"""2단계: 검토 기록(labels_corrections.tsv)과 기본 모델 결과를 합쳐 줄 라벨을 만들고, 학습 전 기준 성능을 잰다.

- 검토한 사진만 다룬다. 검토 기록에 없는 줄은 '초안이 사진과 같다'고 확인한 줄(ok)이다.
- 기준 성능은 '기본 모델이 검출한 줄을 기본 모델이 읽었을 때' 정답 라벨과 비교한 값이다.
  검출 자체를 놓친 글자는 여기 포함되지 않는다(분모 = 검출된 줄 중 라벨이 있는 줄).
- 결과: data/stage2/labels_stage2.json, results/stage2_baseline.json
"""
import json
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).absolute().parents[1]
S2 = EXP / "data" / "stage2"
DICT = EXP / "downloads" / "main_cfg" / "ppocrv5_korean_dict.txt"


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def read_corrections():
    """검토 기록을 읽는다. 같은 줄이 여러 번 나오면 뒤의 것이 우선이다.

    회전(rot180)은 메모와 따로 기억한다. 메모가 'rot180'으로 시작하면 켜지고, 'rot0'으로 시작하면 꺼지며,
    그 밖의 메모로 고쳐 적어도 이전 회전 정보는 그대로 유지된다.
    """
    reviewed, corr, rot = [], {}, {}
    for raw in (S2 / "labels_corrections.tsv").read_text(encoding="utf-8").splitlines():
        if raw.startswith("#reviewed"):
            reviewed.append(raw.split()[1])
            continue
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t") + ["", "", ""]
        corr[parts[0]] = {"status": parts[1], "text": parts[2], "note": parts[3]}
        if parts[3].startswith("rot180"):
            rot[parts[0]] = True
        elif parts[3].startswith("rot0"):
            rot[parts[0]] = False
    return reviewed, corr, rot


def build():
    charset = set(DICT.read_text(encoding="utf-8").splitlines()) | {" "}
    reviewed, corr, rot = read_corrections()
    labels = {}
    for pid in reviewed:
        d = json.loads((S2 / "photos" / f"{pid}.json").read_text(encoding="utf-8"))
        for l in d["lines"]:
            if "crop" not in l:
                continue
            c = corr.get(l["line_id"], {"status": "ok", "text": l["draft"], "note": ""})
            if c["status"] == "ok" and not c["text"]:
                c = {**c, "status": "exclude"}
            labels[l["line_id"]] = {
                "photo": pid, "source": d["source"], "crop": l["crop"],
                "text": c["text"], "status": c["status"], "note": c["note"],
                "rot180": rot.get(l["line_id"], False),
                "draft": l["draft"], "score": l["score"],
                "label_out_of_dict": sorted({ch for ch in c["text"] if ch not in charset}),
            }
    return reviewed, labels


def score(labels, statuses):
    agg = defaultdict(lambda: {"lines": 0, "exact": 0, "exact_nospace": 0, "edits": 0, "chars": 0})
    for v in labels.values():
        if v["status"] not in statuses:
            continue
        for key in ("all", "real" if v["source"] == "real" else "qa"):
            a = agg[key]
            a["lines"] += 1
            a["exact"] += v["draft"] == v["text"]
            a["exact_nospace"] += v["draft"].replace(" ", "") == v["text"].replace(" ", "")
            a["edits"] += edit_distance(v["draft"], v["text"])
            a["chars"] += len(v["text"])
    for a in agg.values():
        a["exact_rate"] = round(a["exact"] / a["lines"], 4) if a["lines"] else None
        a["exact_nospace_rate"] = round(a["exact_nospace"] / a["lines"], 4) if a["lines"] else None
        a["cer"] = round(a["edits"] / a["chars"], 4) if a["chars"] else None
    return dict(agg)


def main():
    reviewed, labels = build()
    (S2 / "labels_stage2.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    status_count = defaultdict(int)
    for v in labels.values():
        status_count[v["status"]] += 1
    out = {
        "what": "학습 전 기본 모델(PP-OCRv5_server_det + korean_PP-OCRv5_mobile_rec) 줄 단위 인식 기준",
        "settings": "긴 변 1600px 축소, enable_mkldnn=False, use_textline_orientation=False, 줄 회전 보정 없음",
        "denominator": "검토한 사진에서 기본 모델이 검출한 줄 중 라벨이 있는 줄 (검출 누락은 미포함)",
        "photos_reviewed": len(reviewed),
        "line_status": dict(status_count),
        "ok_only": score(labels, {"ok"}),
        "ok_and_unsure": score(labels, {"ok", "unsure"}),
    }
    (EXP / "results").mkdir(exist_ok=True)
    (EXP / "results" / "stage2_baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
