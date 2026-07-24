from __future__ import annotations

import math
import pickle
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torchvision import models, transforms


IMAGE_SIZE = 224
RESIZE_SIZE = 256
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class ModelCheckpointError(RuntimeError):
    """Raised when a symbol checkpoint is unsafe, corrupt, or incompatible."""


def build_resnet18(
    class_count: int,
    *,
    pretrained: bool = False,
    dropout: float = 0.3,
) -> nn.Module:
    weights = models.ResNet18_Weights.DEFAULT if pretrained else None
    model = models.resnet18(weights=weights)
    input_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Dropout(p=dropout),
        nn.Linear(input_features, class_count),
    )
    return model


def build_evaluation_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((RESIZE_SIZE, RESIZE_SIZE)),
            transforms.CenterCrop(IMAGE_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=IMAGENET_MEAN,
                std=IMAGENET_STD,
            ),
        ]
    )


def _validate_checkpoint(checkpoint: Any, model_path: str) -> dict:
    if not isinstance(checkpoint, dict):
        raise ModelCheckpointError(
            f"Symbol checkpoint must be a dictionary: {model_path}"
        )

    required = {"model_state_dict", "class_names"}
    missing = required - checkpoint.keys()
    if missing:
        raise ModelCheckpointError(
            "Symbol checkpoint is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )

    class_names = checkpoint["class_names"]
    if (
        not isinstance(class_names, (list, tuple))
        or not class_names
        or not all(isinstance(name, str) and name.strip() for name in class_names)
    ):
        raise ModelCheckpointError(
            "Symbol checkpoint class_names must contain non-empty strings."
        )

    normalized_class_names = [name.strip() for name in class_names]
    if len(set(normalized_class_names)) != len(normalized_class_names):
        raise ModelCheckpointError(
            "Symbol checkpoint class_names contains duplicate values."
        )

    state_dict = checkpoint["model_state_dict"]
    if (
        not isinstance(state_dict, Mapping)
        or not state_dict
        or not all(isinstance(key, str) for key in state_dict)
    ):
        raise ModelCheckpointError(
            "Symbol checkpoint model_state_dict is invalid."
        )

    thresholds = checkpoint.get("thresholds")
    threshold_values: list[float] | None = None
    if thresholds is not None:
        if isinstance(thresholds, (str, bytes)) or not isinstance(
            thresholds,
            Sequence,
        ):
            raise ModelCheckpointError(
                "Symbol checkpoint thresholds must be an array."
            )
        if len(thresholds) != len(normalized_class_names):
            raise ModelCheckpointError(
                "Symbol checkpoint threshold count does not match class count."
            )
        try:
            threshold_values = [float(value) for value in thresholds]
        except (TypeError, ValueError) as exc:
            raise ModelCheckpointError(
                "Symbol checkpoint thresholds must be numeric."
            ) from exc
        if any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for value in threshold_values
        ):
            raise ModelCheckpointError(
                "Symbol checkpoint thresholds must be between 0 and 1."
            )

    config = checkpoint.get("config")
    if config is not None and not isinstance(config, Mapping):
        raise ModelCheckpointError(
            "Symbol checkpoint config must be a dictionary."
        )

    validated = dict(checkpoint)
    validated["class_names"] = normalized_class_names
    if threshold_values is not None:
        validated["thresholds"] = threshold_values
    return validated


def safe_load_checkpoint(
    model_path: str,
    *,
    map_location: str | torch.device,
) -> dict:
    path = Path(model_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Symbol model file does not exist: {path}")

    try:
        checkpoint = torch.load(
            str(path),
            map_location=map_location,
            weights_only=True,
        )
    except TypeError as exc:
        raise ModelCheckpointError(
            "The installed PyTorch version does not support safe "
            "weights_only checkpoint loading."
        ) from exc
    except (
        EOFError,
        OSError,
        RuntimeError,
        ValueError,
        pickle.UnpicklingError,
    ) as exc:
        raise ModelCheckpointError(
            f"Could not safely load symbol checkpoint: {path}"
        ) from exc

    return _validate_checkpoint(checkpoint, str(path))


def load_symbol_model(
    model_path: str,
    *,
    device: str | torch.device,
) -> tuple[nn.Module, list[str], list[float]]:
    checkpoint = safe_load_checkpoint(model_path, map_location=device)
    class_names = list(checkpoint["class_names"])
    state_dict = checkpoint["model_state_dict"]

    model = build_resnet18(len(class_names), pretrained=False)
    if "fc.weight" in state_dict:
        # Compatibility with the first checkpoint format that had no dropout.
        base_model = models.resnet18(weights=None)
        base_model.fc = nn.Linear(base_model.fc.in_features, len(class_names))
        model = base_model

    try:
        model.load_state_dict(state_dict)
    except RuntimeError as exc:
        raise ModelCheckpointError(
            "Symbol checkpoint architecture does not match ResNet18."
        ) from exc

    model = model.to(device)
    model.eval()

    thresholds = checkpoint.get("thresholds")
    if thresholds is None:
        config = checkpoint.get("config") or {}
        legacy = config.get("threshold", 0.5)
        try:
            legacy_value = float(legacy)
        except (TypeError, ValueError) as exc:
            raise ModelCheckpointError(
                "Legacy symbol checkpoint threshold must be numeric."
            ) from exc
        if not math.isfinite(legacy_value) or not 0.0 <= legacy_value <= 1.0:
            raise ModelCheckpointError(
                "Legacy symbol checkpoint threshold must be between 0 and 1."
            )
        thresholds = [legacy_value] * len(class_names)

    return model, class_names, [float(value) for value in thresholds]
