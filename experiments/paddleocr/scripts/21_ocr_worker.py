"""이미지를 받아 PaddleOCR(20_read_batch.py와 같은 처리)로 읽는 작업 프로세스. 모델은 한 번만 불러온다.

ocr_compare/scripts/service_paddle_run.py가 서비스 쪽 가상환경에서 이 프로세스를 띄운다.
- 표준 입력: base64로 인코딩한 이미지 한 줄. 입력이 끝나면 종료한다.
- 표준 출력: 준비되면 `@@READY`, 이미지마다 `@@RESULT <JSON>` 한 줄. 나머지 줄은 Paddle 로그다.
"""
import argparse
import base64
import importlib
import json
import sys
import time
from io import BytesIO
from pathlib import Path

SCRIPTS = Path(__file__).absolute().parent
sys.path.insert(0, str(SCRIPTS))
batch = importlib.import_module("20_read_batch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--textline-orientation", action="store_true")
    parser.add_argument("--max-side", type=int, default=1600)
    args = parser.parse_args()
    models = batch.load_models(SCRIPTS.parent, "PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec", {},
                               "PP-LCNet_x1_0_textline_ori" if args.textline_orientation else None)
    print("@@READY", flush=True)
    for line in sys.stdin:
        started = time.perf_counter()
        # 휴대폰 사진의 EXIF 회전을 적용한다. Vision 좌표도 회전을 적용한 기준이다.
        image = batch.read_image(BytesIO(base64.b64decode(line)), True)
        result = batch.read_lines(image, models, args.max_side)
        result.update(seconds=round(time.perf_counter() - started, 3), peak_rss_mb=batch.peak_rss_mb())
        print("@@RESULT " + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
