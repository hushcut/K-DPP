from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.service.response_contract import normalize_label_response


def test_normalize_label_response_keeps_the_existing_json_value_types() -> None:
    result = normalize_label_response(
        {
            "status": "success",
            "materials": {"cotton": 100},
            "confidence": {"ocr": "high", "parser": "high"},
        },
        api_version="1.0",
    )

    assert result["materials"] == {"cotton": 100}
    assert isinstance(result["materials"]["cotton"], int)
    assert result["confidence"] == {"ocr": "high", "parser": "high"}


def test_normalize_label_response_rejects_invalid_material_ratio_type() -> None:
    with pytest.raises(ValidationError, match="materials"):
        normalize_label_response(
            {"status": "success", "materials": {"cotton": "not-a-number"}},
            api_version="1.0",
        )
