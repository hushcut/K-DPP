from pathlib import Path

import pytest
import torch

from apps.symbol.model_io import (
    ModelCheckpointError,
    safe_load_checkpoint,
)


def test_safe_load_rejects_missing_required_keys(tmp_path: Path) -> None:
    model_path = tmp_path / "missing-keys.pt"
    torch.save({"class_names": ["wash_30"]}, model_path)

    with pytest.raises(ModelCheckpointError, match="required keys"):
        safe_load_checkpoint(str(model_path), map_location="cpu")


def test_safe_load_rejects_duplicate_class_names(tmp_path: Path) -> None:
    model_path = tmp_path / "duplicate-classes.pt"
    torch.save(
        {
            "model_state_dict": {"layer.weight": torch.ones(1)},
            "class_names": ["wash_30", " wash_30 "],
        },
        model_path,
    )

    with pytest.raises(ModelCheckpointError, match="duplicate"):
        safe_load_checkpoint(str(model_path), map_location="cpu")


def test_safe_load_normalizes_class_names_and_thresholds(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "valid.pt"
    torch.save(
        {
            "model_state_dict": {"layer.weight": torch.ones(1)},
            "class_names": [" wash_30 "],
            "thresholds": ["0.65"],
        },
        model_path,
    )

    checkpoint = safe_load_checkpoint(str(model_path), map_location="cpu")

    assert checkpoint["class_names"] == ["wash_30"]
    assert checkpoint["thresholds"] == [0.65]
