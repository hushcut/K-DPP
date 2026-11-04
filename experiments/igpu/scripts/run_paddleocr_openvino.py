"""PaddleOCR 모델의 추론만 OpenVINO로 바꿔 사진을 읽는다.

축소·검출 후처리·줄 자르기·글자 디코딩은 paddleocr/scripts/20_read_batch.py와 PaddleX 코드를 그대로 쓰고,
결과 형식도 같다. experiments/igpu/paddle/venv에서 실행하며 모델은 convert_paddleocr.py로 먼저 변환한다.
"""
import argparse
import hashlib
import importlib
import json
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

PADDLE = Path(__file__).resolve().parents[2] / "paddleocr"
sys.path.insert(0, str(PADDLE / "scripts"))
batch = importlib.import_module("20_read_batch")

import openvino as ov
import psutil
from paddlex.inference.models.base.predictor.base_predictor import BasePredictor

DET_MODEL = "PP-OCRv5_server_det"
REC_MODEL = "korean_PP-OCRv5_mobile_rec"


class OpenVinoInfer:
    """PaddleInfer 자리에 들어가 입력 배치를 받아 출력 배열 목록을 돌려준다."""

    def __init__(self, compiled):
        self.outputs = compiled.outputs
        self.request = compiled.create_infer_request()
        self.seconds = 0.0
        self.calls = 0

    def __call__(self, x):
        started = time.perf_counter()
        result = self.request.infer({0: x[0]})
        self.seconds += time.perf_counter() - started
        self.calls += 1
        return [result[output].copy() for output in self.outputs]


def compile_model(core, name, device, precision, threads):
    config = {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f32" if device == "CPU" else precision}
    if device == "CPU":
        config["INFERENCE_NUM_THREADS"] = threads
    return core.compile_model(core.read_model(str(PADDLE / "models" / "onnx" / f"{name}.onnx")), device, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path, help="id/source/sha256 목록 JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--det-device", choices=("CPU", "GPU"), required=True)
    parser.add_argument("--rec-device", choices=("CPU", "GPU"), required=True)
    parser.add_argument("--gpu-precision", choices=("f32", "f16"), default="f32", help="OpenVINO GPU 기본값은 f16이라 명시한다.")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--exif-transpose", action="store_true")
    parser.add_argument("--max-side", type=int, default=1600)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")
    requested = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    for item in requested:
        if Path(item["source"]).name != item["source"] or not item["id"].replace("_", "").isalnum():
            raise ValueError("사진 목록 형식이 올바르지 않습니다.")
        if hashlib.sha256((args.photos / item["source"]).read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{item['id']}: 사진 목록의 해시와 원본이 다릅니다.")
    settings = {
        "engine": "openvino", "det_model": DET_MODEL, "rec_model": REC_MODEL, "textline_orientation_model": None,
        "det_params": {}, "max_side": args.max_side, "max_pixels": None, "exif_transpose": args.exif_transpose,
        "det_device": args.det_device, "rec_device": args.rec_device, "gpu_precision": args.gpu_precision,
        "threads": args.threads, "python": platform.python_version(),
        "packages": {name: version(name) for name in
                     ("openvino", "paddle2onnx", "paddlepaddle", "paddleocr", "paddlex", "numpy", "opencv-contrib-python", "Pillow")},
    }
    core = ov.Core()
    core.set_property({"CACHE_DIR": str(PADDLE / "models" / "onnx" / "ov_cache")})
    load_started = time.perf_counter()
    infers = {DET_MODEL: OpenVinoInfer(compile_model(core, DET_MODEL, args.det_device, args.gpu_precision, args.threads)),
              REC_MODEL: OpenVinoInfer(compile_model(core, REC_MODEL, args.rec_device, args.gpu_precision, args.threads))}
    settings["compile_seconds"] = round(time.perf_counter() - load_started, 3)
    # Paddle 모델을 불러오지 않도록 PaddleX가 추론기를 만드는 자리를 바꾼다.
    BasePredictor.create_static_infer = lambda self: infers[self.model_name]
    models = batch.load_models(PADDLE, DET_MODEL, REC_MODEL, {})
    settings["model_load_seconds"] = round(time.perf_counter() - load_started, 3)
    args.output.mkdir(parents=True)
    (args.output / "run_config.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"compile_seconds": settings["compile_seconds"], "model_load_seconds": settings["model_load_seconds"]}), flush=True)
    summary = []
    for item in requested:
        photo = args.photos / item["source"]
        det, rec = infers[DET_MODEL], infers[REC_MODEL]
        det_before, rec_before = det.seconds, rec.seconds
        started = time.perf_counter()
        image = batch.read_image(photo, args.exif_transpose)
        read = batch.read_lines(image, models, args.max_side)
        seconds = round(time.perf_counter() - started, 3)
        if hashlib.sha256(photo.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("실행 전후 원본 이미지 해시가 다릅니다.")
        lines = read.pop("lines")
        battery = psutil.sensors_battery()
        result = {"id": item["id"], "source_name": photo.name, "source_sha256": item["sha256"],
                  "status": "success", "truncated": False, **read, "inference_seconds": seconds,
                  "det_infer_seconds": round(det.seconds - det_before, 3), "rec_infer_seconds": round(rec.seconds - rec_before, 3),
                  "power_plugged": battery.power_plugged if battery else None,
                  "peak_rss_mb": batch.peak_rss_mb(), "lines": lines}
        out = args.output / item["id"]
        out.mkdir()
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text("\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
        summary.append({key: result[key] for key in ("id", "recognized_lines", "inference_seconds", "det_infer_seconds",
                                                     "rec_infer_seconds", "power_plugged", "peak_rss_mb")})
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
