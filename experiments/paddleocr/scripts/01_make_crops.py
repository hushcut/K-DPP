"""1단계: 사진 몇 장에서 글자 줄을 잘라내고, 기본 모델 출력으로 라벨 초안을 만든다.

라벨 초안은 사진에 적힌 그대로가 정답이어야 하므로, 사람이 확인해야 하는 줄은 표시해 둔다.
사용법: venv\\Scripts\\python.exe scripts\\01_make_crops.py 01 02 03 ...
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from paddleocr import TextDetection, TextRecognition

EXP = Path(__file__).absolute().parents[1]  # 한글 경로를 피하려고 C:\kdpp_ocr_exp 연결로 실행
PHOTOS = Path(r"C:\Users\김승우\Desktop\실사진 데이터셋")
OUT = EXP / "data"
CROPS = OUT / "crops"
DICT = EXP / "downloads" / "main_cfg" / "ppocrv5_korean_dict.txt"
MAX_LINES_PER_PHOTO = 12


def imread_unicode(p):
    # cv2.imread는 한글 경로를 못 읽어서 바이트로 읽는다
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_unicode(p, img):
    ok, buf = cv2.imencode(".jpg", img)
    buf.tofile(str(p))


def crop_quad(img, quad):
    quad = np.array(quad, dtype=np.float32)
    w = int(max(np.linalg.norm(quad[0] - quad[1]), np.linalg.norm(quad[2] - quad[3])))
    h = int(max(np.linalg.norm(quad[0] - quad[3]), np.linalg.norm(quad[1] - quad[2])))
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if h > 1.5 * w:  # 세로로 긴 줄은 눕힌다
        out = np.rot90(out)
    return out


def main(ids):
    CROPS.mkdir(parents=True, exist_ok=True)
    charset = set(DICT.read_text(encoding="utf-8").splitlines()) | {" "}
    det = TextDetection(model_name="PP-OCRv5_server_det",
                        model_dir=str(EXP / "models/base/PP-OCRv5_server_det_infer"),
                        enable_mkldnn=False)
    rec = TextRecognition(model_name="korean_PP-OCRv5_mobile_rec",
                          model_dir=str(EXP / "models/base/korean_PP-OCRv5_mobile_rec_infer"),
                          enable_mkldnn=False)
    rows = []
    for pid in ids:
        img = imread_unicode(PHOTOS / f"{pid}.jpg")
        # 사진이 커서 긴 변 1600px로 줄여 검출 속도를 맞춘다
        s = 1600 / max(img.shape[:2])
        if s < 1:
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        res = list(det.predict(img))[0]
        polys = sorted(res["dt_polys"], key=lambda q: (q[:, 1].min(), q[:, 0].min()))
        crops = [crop_quad(img, q) for q in polys]
        crops = [c for c in crops if c.shape[0] >= 12 and c.shape[1] >= 24]
        recs = list(rec.predict(crops)) if crops else []
        kept = 0
        for i, (c, r) in enumerate(zip(crops, recs)):
            text, score = r["rec_text"].strip(), float(r["rec_score"])
            if not text or kept >= MAX_LINES_PER_PHOTO:
                continue
            name = f"{pid}_{i:02d}.jpg"
            imwrite_unicode(CROPS / name, c)
            oov = sorted({ch for ch in text if ch not in charset})
            rows.append({"crop": f"crops/{name}", "photo": pid, "draft": text,
                         "score": round(score, 4), "out_of_dict": oov,
                         "needs_check": score < 0.9 or bool(oov)})
            kept += 1
        print(pid, "검출", len(polys), "줄, 저장", kept, flush=True)
    (OUT / "draft_labels.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("total", len(rows))


if __name__ == "__main__":
    main(sys.argv[1:])


