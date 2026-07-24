from __future__ import annotations

import io
import warnings
from functools import lru_cache
from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError

from apps.symbol.class_map import CLASS_TO_KO
from apps.symbol.model_io import (
    build_evaluation_transform,
    load_symbol_model,
)


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = (
    BASE_DIR / "models" / "symbol" / "best_symbol_model_exp.pt"
)
DEFAULT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


@lru_cache(maxsize=4)
def _cached_model(
    resolved_model_path: str,
    modified_time_ns: int,
    device_name: str,
):
    # modified_time_ns participates in the key so replacing a checkpoint
    # invalidates the cache without reloading it for every image.
    del modified_time_ns
    return load_symbol_model(
        resolved_model_path,
        device=torch.device(device_name),
    )


def load_model(
    model_path: str = str(DEFAULT_MODEL_PATH),
    *,
    device: str = DEFAULT_DEVICE,
):
    path = Path(model_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"모델 파일이 없습니다: {path}")
    return _cached_model(str(path), path.stat().st_mtime_ns, device)


def _decode_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes:
        raise ValueError("이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"이미지 크기는 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 이하여야 합니다."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as source:
                width, height = source.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"이미지 픽셀 수는 {MAX_IMAGE_PIXELS:,} 이하여야 합니다."
                    )
                source.verify()
            with Image.open(io.BytesIO(image_bytes)) as source:
                return source.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("지원되는 정상 JPG/PNG 이미지가 아닙니다.") from exc
    except Image.DecompressionBombWarning as exc:
        raise ValueError("안전한 처리 범위를 넘는 고해상도 이미지입니다.") from exc


def predict_symbol_bytes(
    image_bytes: bytes,
    *,
    model_path: str = str(DEFAULT_MODEL_PATH),
    device: str = DEFAULT_DEVICE,
) -> dict:
    image = _decode_image(image_bytes)
    model, class_names, thresholds = load_model(
        model_path,
        device=device,
    )
    tensor = build_evaluation_transform()(image).unsqueeze(0)
    tensor = tensor.to(torch.device(device))

    with torch.inference_mode():
        probabilities = torch.sigmoid(model(tensor))[0].cpu().tolist()

    selected: list[dict] = []
    warnings_list: list[str] = []
    for class_name, probability, threshold in zip(
        class_names,
        probabilities,
        thresholds,
    ):
        if probability < threshold:
            continue
        if class_name not in CLASS_TO_KO:
            warnings_list.append(f"missing_korean_label:{class_name}")
        selected.append(
            {
                "symbol_class": class_name,
                "symbol_korean": CLASS_TO_KO.get(class_name, class_name),
                "symbol_confidence": round(float(probability), 4),
                "decision_threshold": round(float(threshold), 4),
            }
        )

    selected.sort(
        key=lambda item: item["symbol_confidence"],
        reverse=True,
    )
    max_probability = max(probabilities) if probabilities else 0.0
    return {
        "status": "success" if selected else "no_symbol",
        "symbols": selected,
        "symbol_class": "; ".join(
            item["symbol_class"] for item in selected
        ),
        "symbol_korean": "; ".join(
            item["symbol_korean"] for item in selected
        ),
        "symbol_confidence": (
            selected[0]["symbol_confidence"] if selected else 0.0
        ),
        "max_model_probability": round(float(max_probability), 4),
        "warnings": warnings_list,
        "input_scope": (
            "symbol_crop_only: 전체 라벨에서 심볼 위치를 검출하는 모델이 아님"
        ),
    }


def predict_symbol(
    image_path: str,
    model_path: str = str(DEFAULT_MODEL_PATH),
    *,
    device: str = DEFAULT_DEVICE,
) -> dict:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {path}")
    return predict_symbol_bytes(
        path.read_bytes(),
        model_path=model_path,
        device=device,
    )
