"""2단계: 기본 모델(학습 전)로 사진 전체를 읽어 기준 기록과 줄 단위 잘라낸 이미지를 만든다.

- 대상: 실사진 06~50 (01~05는 이미 학습에 써서 제외), 1학기 사진 QA001~QA163
- 사진 하나가 끝날 때마다 data/stage2/photos/<사진>.json 을 저장한다.
  이미 있는 사진은 건너뛰므로, 중간에 끊겨도 같은 명령으로 다시 실행하면 이어서 진행된다.
- 라벨 초안(draft)은 기본 모델이 읽은 글자 그대로다. 정답은 사람이 확인해서 따로 만든다.
사용법: venv\\Scripts\\python.exe scripts\\10_stage2_baseline_run.py [사진ID ...]
"""
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from paddleocr import TextDetection, TextRecognition

EXP = Path(__file__).absolute().parents[1]  # C:\kdpp_ocr_exp 연결로 실행
REAL = Path(r"C:\Users\김승우\Desktop\실사진 데이터셋")
QA_ROOT = Path(r"C:\Users\김승우\Desktop\kdpp-dataset\kdpp-dataset")
OUT = EXP / "data" / "stage2"
DICT = EXP / "downloads" / "main_cfg" / "ppocrv5_korean_dict.txt"
LONG_SIDE = 1600  # 1단계와 같은 축소 기준


def photo_list():
    items = [(f"{i:02d}", REAL / f"{i:02d}.jpg", "real") for i in range(6, 51)]
    qa = {p.stem: p for p in QA_ROOT.rglob("QA*.jpg")}
    items += [(k, qa[k], "qa_" + qa[k].parent.name) for k in sorted(qa)]
    return items


def imread_unicode(p):
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_unicode(p, img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    buf.tofile(str(p))


def crop_quad(img, quad):
    quad = np.array(quad, dtype=np.float32)
    w = int(max(np.linalg.norm(quad[0] - quad[1]), np.linalg.norm(quad[2] - quad[3])))
    h = int(max(np.linalg.norm(quad[0] - quad[3]), np.linalg.norm(quad[1] - quad[2])))
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, m, (max(w, 1), max(h, 1)), borderMode=cv2.BORDER_REPLICATE)
    rotated = h > 1.5 * w
    if rotated:  # 세로로 긴 줄은 눕힌다
        out = np.ascontiguousarray(np.rot90(out))
    return out, rotated


def main(only):
    (OUT / "photos").mkdir(parents=True, exist_ok=True)
    (OUT / "crops").mkdir(parents=True, exist_ok=True)
    charset = set(DICT.read_text(encoding="utf-8").splitlines()) | {" "}
    todo = [x for x in photo_list() if not only or x[0] in only]
    todo = [x for x in todo if not (OUT / "photos" / f"{x[0]}.json").exists()]
    print(f"남은 사진 {len(todo)}장", flush=True)
    if not todo:
        return
    det = TextDetection(model_name="PP-OCRv5_server_det",
                        model_dir=str(EXP / "models/base/PP-OCRv5_server_det_infer"),
                        enable_mkldnn=False)
    rec = TextRecognition(model_name="korean_PP-OCRv5_mobile_rec",
                          model_dir=str(EXP / "models/base/korean_PP-OCRv5_mobile_rec_infer"),
                          enable_mkldnn=False)
    for n, (pid, path, source) in enumerate(todo, 1):
        t0 = time.time()
        img = imread_unicode(path)
        oh, ow = img.shape[:2]
        s = min(1.0, LONG_SIDE / max(oh, ow))
        if s < 1:
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        res = list(det.predict(img))[0]
        t_det = time.time() - t0
        polys = sorted(res["dt_polys"], key=lambda q: (q[:, 1].min(), q[:, 0].min()))
        crop_dir = OUT / "crops" / pid
        crop_dir.mkdir(exist_ok=True)
        lines, crops = [], []
        for i, q in enumerate(polys):
            c, rot = crop_quad(img, q)
            entry = {"line_id": f"{pid}_{i:03d}", "poly": np.asarray(q).round(1).tolist(),
                     "rotated": rot, "crop_hw": list(c.shape[:2])}
            if c.shape[0] < 12 or c.shape[1] < 24:
                entry["skipped"] = "too_small"
            else:
                crops.append((entry, c))
            lines.append(entry)
        recs = list(rec.predict([c for _, c in crops])) if crops else []
        for (entry, c), r in zip(crops, recs):
            text = r["rec_text"].strip()
            entry["draft"] = text
            entry["score"] = round(float(r["rec_score"]), 4)
            entry["out_of_dict"] = sorted({ch for ch in text if ch not in charset})
            name = f"{entry['line_id']}.jpg"
            imwrite_unicode(crop_dir / name, c)
            entry["crop"] = f"crops/{pid}/{name}"
        rec_out = {"photo": pid, "source": source, "file": str(path),
                   "orig_hw": [oh, ow], "scale": round(s, 5),
                   "n_det": len(polys), "n_rec": len(recs),
                   "sec_det": round(t_det, 1), "sec_total": round(time.time() - t0, 1),
                   "lines": lines}
        tmp = OUT / "photos" / f"{pid}.json.tmp"
        tmp.write_text(json.dumps(rec_out, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, OUT / "photos" / f"{pid}.json")
        print(f"[{n}/{len(todo)}] {pid} 검출 {len(polys)}줄, 읽음 {len(recs)}줄, "
              f"{rec_out['sec_total']}초", flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
