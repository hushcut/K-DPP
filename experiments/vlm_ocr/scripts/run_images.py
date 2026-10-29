"""기본 OCR 프롬프트로 원본 사진을 로컬 CPU에서 전사한다. 서비스 파서는 별도로 평가한다."""
import argparse
import gc
import hashlib
import json
import os
import platform
import time
from importlib.metadata import version
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import psutil
import torch
from PIL import Image, ImageOps
from transformers import (AutoProcessor, GlmOcrForConditionalGeneration, PaddleOCRVLForConditionalGeneration,
                          StoppingCriteria, StoppingCriteriaList)
from transformers.utils import logging as hf_logging
hf_logging.disable_progress_bar()

ROOT = Path(__file__).resolve().parents[1]
MODELS = {"glm": (GlmOcrForConditionalGeneration, "Text Recognition:"),
          "paddle_vl": (PaddleOCRVLForConditionalGeneration, "OCR:")}
LOOP_GUARD = {"span": 64, "max_unit": 32}


class RepeatTailStop(StoppingCriteria):
    """생성 끝부분 span개 토큰이 max_unit 이하 길이 단위의 반복뿐이면 멈춘다. 반복이 없으면 출력은 그대로다."""

    def __init__(self, start, span, max_unit):
        self.start, self.span, self.max_unit, self.triggered = start, span, max_unit, False

    def __call__(self, input_ids, scores, **kwargs):
        tail = input_ids[0, self.start:][-self.span:].tolist()
        if len(tail) == self.span and any(all(tail[i] == tail[i - unit] for i in range(unit, self.span))
                                          for unit in range(1, self.max_unit + 1)):
            self.triggered = True
        return torch.full((input_ids.shape[0],), self.triggered, dtype=torch.bool, device=input_ids.device)


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=lambda item: sorted(item) if isinstance(item, set) else str(item)), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--input-manifest", type=Path, help="id/source/sha256 목록. 기존 --ids와 함께 쓰지 않는다.")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--exif-transpose", action="store_true", help="휴대폰 사진의 EXIF 회전을 서비스처럼 적용한다.")
    parser.add_argument("--max-pixels", type=int, help="가로×세로가 이 값을 넘으면 비율을 유지해 축소한다.")
    parser.add_argument("--loop-guard", action="store_true", help="같은 단위가 반복되는 생성을 멈추고 미완료로 기록한다.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.input_manifest:
        if args.ids:
            parser.error("--input-manifest와 --ids는 함께 사용할 수 없습니다.")
        requested = json.loads(args.input_manifest.read_text(encoding="utf-8"))
        if not isinstance(requested, list) or not requested:
            raise ValueError("빈 사진 목록은 허용하지 않습니다.")
    else:
        requested = [{"id": pid, "source": f"KakaoTalk_20261003_141807993_{pid}.jpg"}
                     for pid in (args.ids or [f"{i:02d}" for i in range(1, 21)])]
    if len({item["id"] for item in requested}) != len(requested):
        raise ValueError("사진 ID가 중복됐습니다.")
    for item in requested:
        pid = item["id"]
        if not pid or not all(c.isascii() and (c.isalnum() or c in "_-") for c in pid):
            raise ValueError("안전하지 않은 사진 ID입니다.")
        if Path(item["source"]).name != item["source"]:
            raise ValueError("원본은 사진 폴더 안의 단일 파일명이어야 합니다.")
        digest = hashlib.sha256((args.photos / item["source"]).read_bytes()).hexdigest()
        if item.get("sha256") and digest != item["sha256"]:
            raise RuntimeError(f"{pid}: 사진 목록의 해시와 원본이 다릅니다.")
    manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8"))[args.model]
    if args.output.exists() and not args.resume:
        raise FileExistsError("새 결과 폴더 또는 명시적인 resume 옵션을 사용하세요.")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    model_class, prompt = MODELS[args.model]
    settings = {
        "model": args.model, "model_id": manifest["model_id"], "revision": manifest["revision"],
        "device": "cpu", "dtype": "float32", "threads": args.threads, "prompt": prompt,
        "max_new_tokens": args.max_new_tokens, "do_sample": False, "use_cache": True,
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("torch", "torchvision", "transformers", "Pillow", "numpy")},
    }
    # 기존 결과의 재개 비교가 깨지지 않도록 새 옵션은 사용할 때만 기록한다.
    if args.exif_transpose:
        settings["exif_transpose"] = True
    if args.max_pixels:
        settings.update({"max_pixels": args.max_pixels, "resize_resample": "bicubic"})
    if args.loop_guard:
        settings["loop_guard"] = LOOP_GUARD
    config_file = args.output / "run_config.json"
    if config_file.exists():
        if json.loads(config_file.read_text(encoding="utf-8")) != settings:
            raise RuntimeError("재개 대상의 설정이 다릅니다.")
    else:
        dump(config_file, settings)
    started = time.perf_counter()
    processor = AutoProcessor.from_pretrained(
        manifest["local_dir"], local_files_only=True, trust_remote_code=False,
    )
    model, loading = model_class.from_pretrained(
        manifest["local_dir"], local_files_only=True, trust_remote_code=False,
        dtype=torch.float32, attn_implementation="sdpa", output_loading_info=True,
    )
    if loading.get("missing_keys") or loading.get("mismatched_keys"):
        dump(args.output / "loading_problem.json", loading)
        raise RuntimeError("학습되지 않은 누락 파라미터가 있어 실행을 중단했습니다.")
    model.to("cpu").eval()
    load_seconds = time.perf_counter() - started
    processor_config = processor.image_processor.to_dict()
    dump(args.output / "processor_config.json", processor_config)
    dump(args.output / "loading_info.json", {**loading, "model_load_seconds": load_seconds,
                                            "parameters": sum(p.numel() for p in model.parameters())})
    print(json.dumps({"model": args.model, "phase": "loaded", "model_load_seconds": round(load_seconds, 3)}), flush=True)
    rows = []
    process = psutil.Process()
    for item in requested:
        pid = item["id"]
        photo = args.photos / item["source"]
        digest = hashlib.sha256(photo.read_bytes()).hexdigest()
        out = args.output / pid
        if out.exists():
            saved = json.loads((out / "result.json").read_text(encoding="utf-8"))
            if not args.resume or saved.get("source_sha256") != digest or saved.get("settings") != settings:
                raise RuntimeError("기존 사진 결과를 덮어쓰지 않습니다.")
            rows.append(saved)
            continue
        out.mkdir()
        result = {"id": pid, "source_name": photo.name, "source_sha256": digest, "settings": settings}
        t0 = time.perf_counter()
        try:
            with Image.open(photo) as image_file:
                image = (ImageOps.exif_transpose(image_file) if args.exif_transpose else image_file).convert("RGB")
            result["original_hw"] = [image.height, image.width]
            if args.max_pixels and image.width * image.height > args.max_pixels:
                scale = (args.max_pixels / (image.width * image.height)) ** 0.5
                image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                                     Image.Resampling.BICUBIC)
                result["model_input_hw"] = [image.height, image.width]
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ]}]
            inputs = processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt",
            ).to("cpu")
            input_length = inputs["input_ids"].shape[-1]
            guard = RepeatTailStop(input_length, **LOOP_GUARD) if args.loop_guard else None
            with torch.inference_mode():
                output = model.generate(
                    **inputs, max_new_tokens=args.max_new_tokens, do_sample=False, use_cache=True,
                    stopping_criteria=StoppingCriteriaList([guard] if guard else []),
                )
            generated = output[0, input_length:]
            text = processor.decode(generated, skip_special_tokens=True).strip()
            eos = model.generation_config.eos_token_id
            eos_ids = set(eos if isinstance(eos, (list, tuple)) else [eos])
            ended = bool(len(generated) and int(generated[-1]) in eos_ids)
            loop_stopped = bool(guard and guard.triggered and not ended)
            result.update({
                "status": "success", "text": text, "generated_tokens": len(generated),
                "input_tokens": input_length,
                "truncated": bool((len(generated) >= args.max_new_tokens or loop_stopped) and not ended),
            })
            if guard:
                result["loop_stopped"] = loop_stopped
            del inputs, output, generated, image
        except Exception as exc:
            result.update({"status": "error", "text": "", "error_type": type(exc).__name__})
            (out / "error.txt").write_text(str(exc), encoding="utf-8")
        result["inference_seconds"] = round(time.perf_counter() - t0, 3)
        result["source_unchanged"] = hashlib.sha256(photo.read_bytes()).hexdigest() == digest
        result["rss_mb"] = round(process.memory_info().rss / 1024**2, 1)
        result["peak_rss_mb"] = round(getattr(process.memory_info(), "peak_wset", process.memory_info().rss) / 1024**2, 1)
        dump(out / "result.json", result)
        (out / "text.txt").write_text(result["text"] + "\n", encoding="utf-8")
        rows.append(result)
        dump(args.output / "summary.json", [
            {key: value for key, value in row.items() if key not in ("text", "settings")}
            for row in rows
        ])
        print(json.dumps({key: result.get(key) for key in
                          ("id", "status", "inference_seconds", "generated_tokens", "truncated", "rss_mb")}), flush=True)
        if not result["source_unchanged"]:
            raise RuntimeError("원본 이미지 해시가 달라졌습니다.")
        gc.collect()
    if any(row["status"] != "success" or row.get("truncated") for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

