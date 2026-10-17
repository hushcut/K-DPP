"""3단계: 새 프로세스에서 내보낸 추론 모델을 불러와 잘린 줄을 읽는다.

기본 모델과 학습한 모델을 같은 이미지로 비교한다. 같은 사진(01~05)의 줄이라 성능 평가가 아니라
'저장 → 내보내기 → 다시 불러와 읽기'가 되는지 확인하는 용도다.
"""
import json
from pathlib import Path

import cv2
import numpy as np
from paddleocr import TextRecognition

EXP = Path(__file__).absolute().parents[1]
DATA = EXP / "data"


def load(model_dir):
    return TextRecognition(model_name="korean_PP-OCRv5_mobile_rec", model_dir=str(model_dir), enable_mkldnn=False)


def main():
    labels = json.loads((DATA / "labels_reviewed.json").read_text(encoding="utf-8"))["labels"]
    keys = sorted(labels)
    imgs = [cv2.imdecode(np.fromfile(str(DATA / "crops" / f"{k}.jpg"), np.uint8), cv2.IMREAD_COLOR) for k in keys]
    out = {}
    for name, d in [("base", EXP / "models/base/korean_PP-OCRv5_mobile_rec_infer"),
                    ("smoke", EXP / "output/smoke_rec_infer")]:
        rec = load(d)
        out[name] = [(r["rec_text"], round(float(r["rec_score"]), 4)) for r in rec.predict(imgs)]
    rows, summary = [], {}
    for i, k in enumerate(keys):
        gt = labels[k]["text"]
        rows.append({"crop": k, "split": labels[k]["split"], "label": gt,
                     "base": out["base"][i], "smoke": out["smoke"][i]})
    for name in out:
        for split in ("train", "val"):
            sel = [r for r in rows if r["split"] == split]
            summary[f"{name}_{split}_exact"] = f"{sum(r[name][0] == r['label'] for r in sel)}/{len(sel)}"
    (EXP / "results").mkdir(exist_ok=True)
    (EXP / "results" / "reload_read.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        if r["split"] == "val" or r["base"][0] != r["smoke"][0]:
            print(r["split"], r["crop"], "| 정답:", r["label"], "| 기본:", r["base"][0], "| 학습후:", r["smoke"][0])


if __name__ == "__main__":
    main()
