"""사진 목록을 EasyOCR(read_one_image.py와 같은 기본 설정)로 한 번에 읽어 사진별 결과를 기록한다.

모델은 한 번만 불러온다. 결과 형식은 vlm_ocr/scripts/evaluate_batch.py가 바로 읽는
<출력>/<사진 ID>/result.json·text.txt이며, 글자 영역 좌표(polygon)도 함께 남긴다.
"""
import argparse
import ctypes
import hashlib
import json
import platform
import time
from ctypes import wintypes
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np
from easyocr import Reader
from easyocr import easyocr as easyocr_core
from PIL import Image, ImageOps

LANGS = ["ko", "en"]


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path, help="id/source/sha256 목록 JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exif-transpose", action="store_true", help="휴대폰 사진의 EXIF 회전을 서비스처럼 적용한다.")
    parser.add_argument("--rotation-info", type=int, nargs="+")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")
    requested = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    for item in requested:
        if Path(item["source"]).name != item["source"] or not item["id"].replace("_", "").isalnum():
            raise ValueError("사진 목록 형식이 올바르지 않습니다.")
        if hashlib.sha256((args.photos / item["source"]).read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{item['id']}: 사진 목록의 해시와 원본이 다릅니다.")
    exp = Path(__file__).absolute().parents[1]
    load_started = time.perf_counter()
    # 모델은 이미 받아 둔 파일만 쓴다.
    reader = Reader(LANGS, gpu=False, model_storage_directory=str(exp / "models"),
                    download_enabled=False, verbose=False)
    settings = {
        "langs": LANGS, "detector": "craft_mlt_25k", "recognizer": "korean_g2",
        "rotation_info": args.rotation_info, "exif_transpose": args.exif_transpose, "device": "cpu",
        "python": platform.python_version(), "model_load_seconds": round(time.perf_counter() - load_started, 3),
        "packages": {name: version(name) for name in
                     ("easyocr", "torch", "torchvision", "numpy", "opencv-python-headless", "Pillow")},
    }
    args.output.mkdir(parents=True)
    (args.output / "run_config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = []
    for item in requested:
        photo = args.photos / item["source"]
        started = time.perf_counter()
        with Image.open(photo) as image_file:
            rgb = np.asarray((ImageOps.exif_transpose(image_file) if args.exif_transpose
                              else image_file).convert("RGB"))
        grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        # read_one_image.py처럼 컬러(RGB)와 흑백 입력을 직접 넘긴다.
        easyocr_core.reformat_input = lambda _image, rgb=rgb, grey=grey: (rgb, grey)
        raw = reader.readtext(rgb, rotation_info=args.rotation_info)
        raw = sorted(raw, key=lambda r: (min(p[1] for p in r[0]), min(p[0] for p in r[0])))
        lines = [{"index": index, "polygon": [[float(x), float(y)] for x, y in box],
                  "text": text.strip(), "score": round(float(score), 4)}
                 for index, (box, text, score) in enumerate(raw)]
        seconds = round(time.perf_counter() - started, 3)
        if hashlib.sha256(photo.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("실행 전후 원본 이미지 해시가 다릅니다.")
        result = {"id": item["id"], "source_name": photo.name, "source_sha256": item["sha256"],
                  "status": "success", "truncated": False, "original_hw": list(grey.shape[:2]), "scale": 1.0,
                  "recognized_lines": len(lines), "inference_seconds": seconds,
                  "peak_rss_mb": peak_rss_mb(), "lines": lines}
        out = args.output / item["id"]
        out.mkdir()
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text("\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
        summary.append({key: result[key] for key in ("id", "recognized_lines", "inference_seconds", "peak_rss_mb")})
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
