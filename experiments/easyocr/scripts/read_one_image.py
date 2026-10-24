"""EasyOCR 기본 설정으로 원본 사진 한 장을 읽고 결과를 별도 폴더에 기록한다.

paddleocr/scripts/04_read_one_image.py와 같은 결과 형식(result.json, text.txt)을 쓴다.
"""
import argparse
import hashlib
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np
from easyocr import Reader
from easyocr import easyocr as easyocr_core
from easyocr.imgproc import loadImage

LANGS = ["ko", "en"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rotation-info", type=int, nargs="+",
                        help="EasyOCR rotation_info. 예: 90 180 270 (각 줄을 돌려 읽고 점수가 높은 쪽을 고른다)")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")
    image_hash = hashlib.sha256(args.image.read_bytes()).hexdigest()
    exp = Path(__file__).absolute().parents[1]
    started = time.perf_counter()
    reader = Reader(LANGS, gpu=False, model_storage_directory=str(exp / "models"),
                    download_enabled=True, verbose=False)
    load_seconds = time.perf_counter() - started
    # 파일 경로 입력과 같은 이미지(RGB 컬러 + 흑백)를 만들되, 한글 경로에서 cv2.imread가 실패하지 않게 바이트로 읽는다.
    image = loadImage(str(args.image))
    grey = cv2.imdecode(np.fromfile(str(args.image), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or grey is None:
        raise ValueError("입력 이미지를 읽지 못했습니다.")
    easyocr_core.reformat_input = lambda _: (image, grey)
    inference_started = time.perf_counter()
    raw = reader.readtext(str(args.image), rotation_info=args.rotation_info)
    inference_seconds = time.perf_counter() - inference_started
    raw = sorted(raw, key=lambda r: (min(p[1] for p in r[0]), min(p[0] for p in r[0])))
    lines = [{"index": index, "polygon": [[float(x), float(y)] for x, y in box],
              "text": text.strip(), "score": round(float(score), 4)}
             for index, (box, text, score) in enumerate(raw)]
    unchanged = hashlib.sha256(args.image.read_bytes()).hexdigest() == image_hash
    if not unchanged:
        raise RuntimeError("실행 전후 원본 이미지 해시가 다릅니다.")
    result = {
        "source_name": args.image.name, "source_sha256": image_hash,
        "source_unchanged": unchanged, "original_hw": list(grey.shape[:2]), "scale": 1.0,
        "python": platform.python_version(),
        "packages": {name: version(name) for name in
                     ("easyocr", "torch", "torchvision", "numpy", "opencv-python-headless")},
        "device": "cpu", "langs": LANGS, "rotation_info": args.rotation_info,
        "detector": "craft_mlt_25k", "recognizer": "korean_g2",
        "detected_lines": len(lines), "recognized_lines": len(lines),
        "model_load_seconds": round(load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3), "lines": lines,
    }
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "text.txt").write_text(
        "\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "lines"},
                     ensure_ascii=False, indent=2))
    for line in lines:
        print(f"{line['score']:.4f}\t{line['text']}")


if __name__ == "__main__":
    main()
