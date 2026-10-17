"""2단계: 같은 옷(또는 같은 라벨 문구)의 사진을 한 묶음으로 만들고, 묶음 단위로 학습/검증을 나눈다.

- 묶음 근거 1: 검토 기록(labels_corrections.tsv)의 '#same' 줄 (사진을 보고 같은 옷이라고 판단)
- 묶음 근거 2: 코디네이터가 알려 준 실사진-1학기 사진 겹침 (아래 KNOWN)
- 묶음 근거 3: 다른 옷이지만 라벨 문구가 거의 같은 경우 (아래 TEMPLATE). 검증에 같은 문구가 새지 않게 보수적으로 묶었다.
- 검증 묶음은 무작위(seed 고정)로 골라 확정·확인필요 줄의 약 20%가 되게 한다.
- 결과: data/stage2/garment_groups.json, data/stage2/train_list.txt, val_list.txt, unsure_list.tsv
  학습 목록 형식은 PaddleOCR 인식 학습 형식(이미지 경로<TAB>정답)이고, 확정(ok) 줄만 넣는다.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).absolute().parents[1]
S2 = EXP / "data" / "stage2"
VAL_SHARE = 0.20
SEED = 20261017

KNOWN = [["QA125", "20", "26"], ["QA038", "QA129", "38"], ["QA136", "24", "29"],
         ["QA122", "25"], ["QA127", "21"]]
TEMPLATE = [["QA037", "QA038"], ["QA027", "QA030"], ["QA129", "QA130"],
            ["17", "31", "44"], ["14", "15", "34", "35"],
            ["QA144", "QA145", "QA151", "QA148", "QA149", "QA150"],
            ["22", "QA002", "QA128"]]


def main():
    labels = json.loads((S2 / "labels_stage2.json").read_text(encoding="utf-8"))
    photos = sorted({v["photo"] for v in labels.values()} | {p.stem for p in (S2 / "photos").glob("*.json")})
    parent = {p: p for p in photos}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(ids):
        for a in ids[1:]:
            parent[find(a)] = find(ids[0])

    same = [l.split()[1:] for l in (S2 / "labels_corrections.tsv").read_text(encoding="utf-8").splitlines()
            if l.startswith("#same")]
    for ids in same + KNOWN + TEMPLATE:
        ids = [p for p in ids if p in parent]  # 일부 사진만 처리한 경우 없는 사진은 건너뛴다
        if len(ids) > 1:
            union(ids)

    groups = defaultdict(list)
    for p in photos:
        groups[find(p)].append(p)
    lines = defaultdict(int)
    for v in labels.values():
        if v["status"] in ("ok", "unsure"):
            lines[find(v["photo"])] += 1

    keys = sorted(groups)
    random.Random(SEED).shuffle(keys)
    total = sum(lines.values())
    val, acc = set(), 0
    for k in keys:
        if acc >= VAL_SHARE * total:
            break
        if acc + lines[k] > (VAL_SHARE + 0.03) * total:  # 너무 큰 묶음은 건너뛰어 비율을 맞춘다
            continue
        val.add(k)
        acc += lines[k]

    out_groups = []
    for i, k in enumerate(sorted(groups, key=lambda k: sorted(groups[k])[0])):
        out_groups.append({"group": f"G{i:03d}", "photos": sorted(groups[k]),
                           "split": "val" if k in val else "train", "labeled_lines": lines[k]})
    split_of = {p: g["split"] for g in out_groups for p in g["photos"]}
    (S2 / "garment_groups.json").write_text(json.dumps(out_groups, ensure_ascii=False, indent=1), encoding="utf-8")

    # 사진이 거꾸로 찍혀 글자가 180도 뒤집힌 줄은 학습용으로 바로 세운 사본을 쓴다(원본 crop은 기준 측정용으로 그대로 둔다)
    from PIL import Image
    (S2 / "crops_upright").mkdir(exist_ok=True)
    rows = {"train": [], "val": []}
    rows_all = {"train": [], "val": []}  # 한국어 모델 사전 밖 글자(일본어·중국어 등)가 든 줄까지 포함
    unsure = ["line_id\tsplit\tcrop\tbest_reading\tnote"]
    for lid, v in sorted(labels.items()):
        sp = split_of[v["photo"]]
        v["split"] = sp
        crop = v["crop"]
        if v["rot180"] and v["status"] != "exclude":
            crop = f"crops_upright/{lid}.jpg"
            Image.open(S2 / v["crop"]).rotate(180).save(S2 / crop, quality=95)
        if v["status"] == "ok":
            row = f"stage2/{crop}\t{v['text']}"  # 학습 설정의 data_dir = C:/kdpp_ocr_exp/data/
            rows_all[sp].append(row)
            if not v["label_out_of_dict"]:
                rows[sp].append(row)
        elif v["status"] == "unsure":
            unsure.append(f"{lid}\t{sp}\t{v['crop']}\t{v['text']}\t{v['note']}")
    (S2 / "labels_stage2.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    for sp in rows:
        (S2 / f"{sp}_list.txt").write_text("\n".join(rows[sp]) + "\n", encoding="utf-8")
        (S2 / f"{sp}_list_all_chars.txt").write_text("\n".join(rows_all[sp]) + "\n", encoding="utf-8")
    (S2 / "unsure_list.tsv").write_text("\n".join(unsure) + "\n", encoding="utf-8")

    n_val_g = sum(g["split"] == "val" for g in out_groups)
    print(f"사진 {len(photos)}장, 옷 묶음 {len(out_groups)}개 (검증 {n_val_g}개)")
    print(f"확정 줄(한국어 사전 안): 학습 {len(rows['train'])}, 검증 {len(rows['val'])}; "
          f"사전 밖 글자 포함 시 {len(rows_all['train'])}/{len(rows_all['val'])}; 확인 필요 {len(unsure) - 1}")
    sys.path.insert(0, str(EXP / "scripts"))
    from importlib import import_module
    score = import_module("12_labels_and_baseline").score
    by_split = {sp: score({k: v for k, v in labels.items() if v["split"] == sp}, {"ok"}) for sp in ("train", "val")}
    res = EXP / "results" / "stage2_baseline.json"
    base = json.loads(res.read_text(encoding="utf-8"))
    base["ok_only_by_split"] = by_split
    base["split"] = {"groups": len(out_groups), "val_groups": n_val_g, "seed": SEED,
                     "ok_lines_korean_dict": {sp: len(r) for sp, r in rows.items()},
                     "ok_lines_all_chars": {sp: len(r) for sp, r in rows_all.items()}, "unsure_lines": len(unsure) - 1}
    res.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    print("검증 줄 기준(학습 전):", by_split["val"].get("all", "검증 줄 없음"))
    for sp in ("train", "val"):
        src = defaultdict(int)
        for g in out_groups:
            if g["split"] == sp:
                for p in g["photos"]:
                    src["qa" if p.startswith("QA") else "real"] += 1
        print(sp, dict(src))


if __name__ == "__main__":
    main()
