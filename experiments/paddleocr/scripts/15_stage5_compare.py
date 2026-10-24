"""5단계: 학습 전 모델과 학습한 모델이 같은 검증 줄을 같은 방식으로 읽게 해 비교한다.

- 대상: data/stage2/val_list.txt (옷 단위 분할의 검증 묶음, 한국어 사전 안 글자만, 확정 줄)
- 읽기: 내보낸 추론 모델을 paddleocr TextRecognition으로 불러와 잘린 줄 이미지를 원래 비율대로 읽는다
  (학습 중 검증처럼 폭 320으로 누르거나 25자 이상 줄을 빼지 않는다).
- 지표: 정확 일치, 띄어쓰기 무시 일치, CER(편집 거리 합 / 정답 글자 수 합)
- 참고: 학습 전 모델의 결과는 2단계 기준(전체 사진 파이프라인 초안)과 조금 다를 수 있다.
  비교는 이 스크립트 안의 두 모델끼리만 한다.

사용: python scripts/15_stage5_compare.py [모델이름=추론모델폴더 ...]
결과: results/stage5_compare.json
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from paddleocr import TextRecognition

EXP = Path(__file__).absolute().parents[1]
DATA = EXP / "data"
S2 = DATA / "stage2"
MATERIAL = re.compile(
    r"%|겉감|안감|배색|충전|면|폴리|나일론|레이온|울|아크릴|스판|린넨|실크|캐시미어|모달|비스코스|"
    r"COTTON|POLY|NYLON|RAYON|WOOL|ACRYL|SPANDEX|ELASTANE|LINEN|VISCOSE|MODAL|SILK|CASHMERE|LYOCELL|"
    r"TENCEL|SHELL|LINING|BODY", re.IGNORECASE)
DEFAULT_MODELS = {
    "base": EXP / "models/base/korean_PP-OCRv5_mobile_rec_infer",
    "stage5_best": EXP / "output/stage5_rec_infer_best",
}


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(pairs):
    n = len(pairs)
    if not n:
        return {"lines": 0}
    exact = sum(p == t for p, t in pairs)
    nospace = sum(p.replace(" ", "") == t.replace(" ", "") for p, t in pairs)
    edits = sum(edit_distance(p, t) for p, t in pairs)
    chars = sum(len(t) for _p, t in pairs)
    return {"lines": n, "exact": exact, "exact_rate": round(exact / n, 4),
            "exact_nospace_rate": round(nospace / n, 4), "edits": edits, "chars": chars,
            "cer": round(edits / chars, 4)}


def main():
    models = dict(DEFAULT_MODELS)
    for arg in sys.argv[1:]:
        name, path = arg.split("=", 1)
        models[name] = Path(path)
    rows = [line.rstrip("\n").split("\t", 1) for line in (S2 / "val_list.txt").open(encoding="utf-8") if line.strip()]
    labels = json.loads((S2 / "labels_stage2.json").read_text(encoding="utf-8"))
    items = []
    for rel, text in rows:
        line_id = Path(rel).stem
        info = labels.get(line_id, {})
        items.append({"line_id": line_id, "crop": rel, "label": text, "source": info.get("source", ""),
                      "material_like": bool(MATERIAL.search(text)), "long": len(text) >= 25})
    images = [cv2.imdecode(np.fromfile(str(DATA / it["crop"]), np.uint8), cv2.IMREAD_COLOR) for it in items]
    for name, model_dir in models.items():
        rec = TextRecognition(model_name="korean_PP-OCRv5_mobile_rec", model_dir=str(model_dir), enable_mkldnn=False)
        for it, res in zip(items, rec.predict(images)):
            it[name] = res["rec_text"]
    summary = {}
    groups = {
        "all": items,
        "material_like": [it for it in items if it["material_like"]],
        "long_25plus": [it for it in items if it["long"]],
        "real_photos": [it for it in items if it["source"] == "real"],
        "qa_photos": [it for it in items if it["source"] != "real"],
    }
    for name in models:
        summary[name] = {group: score([(it[name], it["label"]) for it in sel]) for group, sel in groups.items()}
    changed = {"fixed": [], "broken": []}
    if "base" in models and "stage5_best" in models:
        for it in items:
            if it["base"] != it["label"] and it["stage5_best"] == it["label"]:
                changed["fixed"].append(it["line_id"])
            if it["base"] == it["label"] and it["stage5_best"] != it["label"]:
                changed["broken"].append(it["line_id"])
        summary["changes"] = {key: len(value) for key, value in changed.items()}
    (EXP / "results").mkdir(exist_ok=True)
    out = {"what": "stage5 base vs fine-tuned on val_list.txt (same crops, same reader, original aspect)",
           "models": {k: str(v) for k, v in models.items()}, "summary": summary, "changed": changed, "rows": items}
    (EXP / "results" / "stage5_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
