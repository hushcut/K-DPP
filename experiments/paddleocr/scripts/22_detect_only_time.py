"""글자 인식 없이 PaddleOCR 검출만 돌린 시간과 글자 상자 전체 영역을 잰다(20_read_batch.py와 같은 축소·검출 모델).

영역 자르기(vlm_ocr/scripts/make_region_crops.py --region all_text)에 검출만 쓸 때 사진당 얼마나 더 걸리는지 확인하는 용도다.
"""
import argparse
import importlib
import json
import statistics
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).absolute().parent
sys.path.insert(0, str(SCRIPTS))
batch = importlib.import_module("20_read_batch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-side", type=int, default=1600)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    detector = batch.load_models(SCRIPTS.parent, "PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec", {})[0]
    rows = []
    for item in json.loads(args.input_manifest.read_text(encoding="utf-8")):
        started = time.perf_counter()
        image = batch.read_image(args.photos / item["source"], True)
        height, width = image.shape[:2]
        scale = min(1.0, args.max_side / max(height, width))
        if scale < 1:
            image = batch.baseline.cv2.resize(image, None, fx=scale, fy=scale, interpolation=batch.baseline.cv2.INTER_AREA)
        polygons = list(detector.predict(image))[0]["dt_polys"]
        seconds = time.perf_counter() - started
        share = None
        if len(polygons):
            # 좌표가 int16이라 그대로 곱하면 넘친다.
            xs = [int(point[0]) for polygon in polygons for point in polygon]
            ys = [int(point[1]) for polygon in polygons for point in polygon]
            share = (max(xs) - min(xs)) * (max(ys) - min(ys)) / (image.shape[0] * image.shape[1])
        rows.append({"id": item["id"], "seconds": round(seconds, 3), "boxes": len(polygons),
                     "all_box_share": round(float(share), 4) if share is not None else None})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    seconds = [row["seconds"] for row in rows]
    shares = [row["all_box_share"] for row in rows if row["all_box_share"] is not None]
    summary = {"photos": len(rows), "median_seconds": round(statistics.median(seconds), 1), "max_seconds": round(max(seconds), 1),
               "within_10s": sum(s <= 10 for s in seconds), "median_all_box_share": round(statistics.median(shares), 3),
               "peak_rss_mb": batch.peak_rss_mb()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
