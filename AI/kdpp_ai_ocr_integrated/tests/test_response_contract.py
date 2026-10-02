from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.service.response_contract import failed_label_response, normalize_label_response


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


def test_confirmed_composition_evidence_is_preserved() -> None:
    result = normalize_label_response(
        {
            "status": "success",
            "materials": {"cotton": 80, "polyester": 20},
            "parse_evidence": {"composition_status": "confirmed"},
        },
        api_version="1.0",
    )

    assert result["parse_evidence"]["composition_status"] == "confirmed"


def test_normalize_label_response_rejects_invalid_material_ratio_type() -> None:
    with pytest.raises(ValidationError, match="materials"):
        normalize_label_response(
            {"status": "success", "materials": {"cotton": "not-a-number"}},
            api_version="1.0",
        )


def test_failure_responses_do_not_share_material_defaults() -> None:
    first = failed_label_response(api_version="1.0", error_code="test", message="실패")
    first["materials"]["cotton"] = 100
    second = failed_label_response(api_version="1.0", error_code="test", message="실패")

    assert second["materials"] == {}


def test_response_nested_values_are_independent_of_the_input() -> None:
    payload = {
        "status": "success",
        "materials": {"cotton": 99.5, "spandex": 0.5},
        "selected_part": "outer",
        "parts": {"outer": {"cotton": 99.5, "spandex": 0.5}},
        "parse_evidence": {"observed_ratios": {"outer": [99.5, 0.5]}},
        "ocr": {"attempts": [{"elapsed_ms": 12}]},
    }
    first = normalize_label_response(payload, api_version="1.0")
    first["materials"]["cotton"] = 1
    first["parts"]["outer"]["cotton"] = 1
    first["parse_evidence"]["observed_ratios"]["outer"].append(1)
    first["ocr"]["attempts"][0]["elapsed_ms"] = 999
    second = normalize_label_response(payload, api_version="1.0")

    assert second["materials"] == {"cotton": 99.5, "spandex": 0.5}
    assert isinstance(second["materials"]["cotton"], float)
    assert second["parts"]["outer"] == payload["materials"]
    assert second["parse_evidence"]["observed_ratios"]["outer"] == [99.5, 0.5]
    assert second["ocr"]["attempts"][0]["elapsed_ms"] == 12


@pytest.mark.parametrize("field", ["materials", "parts"])
@pytest.mark.parametrize(
    "ratio",
    ["100", True, False, float("nan"), float("inf"), -float("inf"), -1, 0, 101,
     Decimal("100")],
)
def test_response_rejects_invalid_ratios_in_representative_and_part_materials(field, ratio):
    payload = {"status": "success", "materials": {"cotton": 100}}
    payload[field] = {"cotton": ratio} if field == "materials" else {"outer": {"cotton": ratio}}

    with pytest.raises(ValidationError, match=field):
        normalize_label_response(payload, api_version="1.0")


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "unknown"},
        {"status": "success", "materials": {}},
        {"status": "success", "materials": {"cotton": 99}},
        {"status": "success", "materials": {"cotton": 60, "polyester": 60}},
        {"status": "failed", "materials": {"cotton": 100}},
        {"status": "success", "materials": {"cotton": 100},
         "parts": {"outer": {"cotton": 99}}, "selected_part": "outer"},
        {"status": "success", "materials": {"cotton": 100},
         "parts": {"outer": {"cotton": 100}}, "selected_part": "lining"},
        {"status": "success", "materials": {"cotton": 100},
         "parts": {"outer": {"polyester": 100}}, "selected_part": "outer"},
    ],
)
def test_response_rejects_inconsistent_success_and_failure(payload) -> None:
    with pytest.raises(ValidationError):
        normalize_label_response(payload, api_version="1.0")


def test_normalization_keeps_the_service_api_version_authoritative() -> None:
    result = normalize_label_response(
        {"status": "failed", "api_version": "unexpected"}, api_version="1.0",
    )
    assert result["api_version"] == "1.0"


def test_failure_extra_cannot_override_the_failure_identity() -> None:
    result = failed_label_response(
        api_version="1.0", error_code="internal_error", message="처리 실패",
        extra={"status": "success", "error_code": "", "message": "성공"},
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "internal_error"
    assert result["message"] == "처리 실패"
