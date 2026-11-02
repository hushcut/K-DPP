"""사진 목록을 PaddleOCR(04_read_one_image.py와 같은 모델·처리)로 한 번에 읽어 사진별 결과를 기록한다.

모델은 한 번만 불러온다. 결과 형식은 vlm_ocr/scripts/evaluate_batch.py가 바로 읽는
<출력>/<사진 ID>/result.json·text.txt이며, 글자 영역 좌표(polygon)도 함께 남긴다.
"""
import argparse
import ctypes
import hashlib
import importlib
import json
import platform
import sys
import time
from ctypes import wintypes
from importlib.metadata import version
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

SCRIPTS = Path(__file__).absolute().parent
sys.path.insert(0, str(SCRIPTS))
baseline = importlib.import_module("10_stage2_baseline_run")


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_rss_mb():
    """Windows 프로세스의 최대 작업 메모리(MB). 다른 OS나 실패 시 None."""
    try:
        counters = _MemoryCounters(cb=ctypes.sizeof(_MemoryCounters))
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MemoryCounters), wintypes.DWORD]
        if not query(current(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.PeakWorkingSetSize / 1024**2, 1)
    except (AttributeError, OSError):
        return None


def read_image(path, exif_transpose):
    with Image.open(path) as image_file:
        image = (ImageOps.exif_transpose(image_file) if exif_transpose else image_file).convert("RGB")
    return np.ascontiguousarray(np.asarray(image)[:, :, ::-1])  # OpenCV 순서(BGR)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path, help="id/source/sha256 목록 JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exif-transpose", action="store_true", help="휴대폰 사진의 EXIF 회전을 서비스처럼 적용한다.")
    parser.add_argument("--textline-orientation", action="store_true")
    parser.add_argument("--det-limit-side-len", type=int)
    parser.add_argument("--det-limit-type", choices=("max", "min"))
    parser.add_argument("--max-side", type=int, default=1600, help="04_read_one_image.py와 같은 입력 긴 변 상한")
    parser.add_argument("--max-pixels", type=int,
                        help="입력 화소 수 상한. 원본 해상도 검출에서 Paddle 3.0.0 CPU 엔진이 약 192만 화소 입력에 비정상 종료됐다(160만은 정상).")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")
    requested = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    for item in requested:
        if Path(item["source"]).name != item["source"] or not item["id"].replace("_", "").isalnum():
            raise ValueError("사진 목록 형식이 올바르지 않습니다.")
        if hashlib.sha256((args.photos / item["source"]).read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{item['id']}: 사진 목록의 해시와 원본이 다릅니다.")
    det_params = {key: value for key, value in {
        "limit_side_len": args.det_limit_side_len, "limit_type": args.det_limit_type}.items() if value is not None}
    exp = SCRIPTS.parent
    settings = {
        "det_model": "PP-OCRv5_server_det", "rec_model": "korean_PP-OCRv5_mobile_rec",
        "textline_orientation_model": "PP-LCNet_x1_0_textline_ori" if args.textline_orientation else None,
        "det_params": det_params, "max_side": args.max_side, "max_pixels": args.max_pixels, "exif_transpose": args.exif_transpose,
        "device": "cpu", "enable_mkldnn": False, "python": platform.python_version(),
        "packages": {name: version(name) for name in
                     ("paddlepaddle", "paddleocr", "paddlex", "numpy", "opencv-contrib-python", "Pillow")},
    }
    load_started = time.perf_counter()
    detector = baseline.TextDetection(model_name=settings["det_model"],
                                      model_dir=str(exp / "models/base/PP-OCRv5_server_det_infer"),
                                      device="cpu", enable_mkldnn=False, **det_params)
    recognizer = baseline.TextRecognition(model_name=settings["rec_model"],
                                          model_dir=str(exp / "models/base/korean_PP-OCRv5_mobile_rec_infer"),
                                          device="cpu", enable_mkldnn=False)
    classifier = None
    if args.textline_orientation:
        from paddleocr import TextLineOrientationClassification
        classifier = TextLineOrientationClassification(
            model_name=settings["textline_orientation_model"],
            model_dir=str(exp / f"models/base/{settings['textline_orientation_model']}_infer"),
            device="cpu", enable_mkldnn=False)
    settings["model_load_seconds"] = round(time.perf_counter() - load_started, 3)
    args.output.mkdir(parents=True)
    (args.output / "run_config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = []
    for item in requested:
        photo = args.photos / item["source"]
        started = time.perf_counter()
        image = read_image(photo, args.exif_transpose)
        original_hw = list(image.shape[:2])
        scale = min(1.0, args.max_side / max(original_hw))
        if args.max_pixels:
            scale = min(scale, (args.max_pixels / (original_hw[0] * original_hw[1])) ** 0.5)
        if scale < 1:
            image = baseline.cv2.resize(image, None, fx=scale, fy=scale, interpolation=baseline.cv2.INTER_AREA)
        detected = list(detector.predict(image))[0]
        polygons = sorted(detected["dt_polys"], key=lambda q: (q[:, 1].min(), q[:, 0].min()))
        kept, skipped = [], 0
        for index, polygon in enumerate(polygons):
            crop, rotated = baseline.crop_quad(image, polygon)
            if crop.shape[0] < 12 or crop.shape[1] < 24:
                skipped += 1
                continue
            kept.append(({"index": index, "polygon": polygon.tolist(), "rotated": rotated}, crop))
        if classifier and kept:
            for i, ((entry, crop), angle) in enumerate(zip(kept, classifier.predict([c for _, c in kept]))):
                entry["textline_angle"] = 180 if int(angle["class_ids"][0]) == 1 else 0
                if entry["textline_angle"] == 180:
                    kept[i] = (entry, baseline.cv2.rotate(crop, baseline.cv2.ROTATE_180))
        predictions = list(recognizer.predict([crop for _, crop in kept])) if kept else []
        if len(predictions) != len(kept):
            raise RuntimeError("글자 영역 수와 인식 결과 수가 다릅니다.")
        lines = [{**entry, "text": result["rec_text"].strip(), "score": round(float(result["rec_score"]), 4)}
                 for (entry, _), result in zip(kept, predictions)]
        seconds = round(time.perf_counter() - started, 3)
        if hashlib.sha256(photo.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("실행 전후 원본 이미지 해시가 다릅니다.")
        result = {"id": item["id"], "source_name": photo.name, "source_sha256": item["sha256"],
                  "status": "success", "truncated": False, "original_hw": original_hw, "scale": scale,
                  "detected_lines": len(polygons), "recognized_lines": len(lines), "skipped_small": skipped,
                  "inference_seconds": seconds, "peak_rss_mb": peak_rss_mb(), "lines": lines}
        out = args.output / item["id"]
        out.mkdir()
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text("\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
        summary.append({key: result[key] for key in ("id", "recognized_lines", "inference_seconds", "peak_rss_mb")})
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
