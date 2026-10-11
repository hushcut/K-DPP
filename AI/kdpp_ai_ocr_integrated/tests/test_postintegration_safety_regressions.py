"""Public-response regressions for the independent post-integration audit."""

import json

import pytest
from fastapi.testclient import TestClient

from apps.service.label_analysis import analyze_label_text
from apps.service.main import app
from apps.text.parse_label import parse_materials


def assert_rejected(text: str) -> None:
    # analyze_label_text also validates the service response contract. A parser
    # rejection must remain a serializable response, rather than a service 500.
    response = analyze_label_text(text)
    assert response["status"] == "failed", response
    assert response["materials"] == {}
    assert response["parts"] == {}
    assert response["selected_part"] == ""
    assert response["error_code"]
    assert json.loads(json.dumps(response, allow_nan=False)) == response
    assert parse_materials(text) == {}


@pytest.mark.parametrize(
    "unconfirmed_row",
    [
        pytest.param("UNKNOWN 50%", id="explicit-unknown"),
        pytest.param("알 수 없는 소재 50%", id="korean-unknown"),
        pytest.param("未知纤维 50%", id="chinese-unknown-fiber"),
    ],
)
def test_standalone_unknown_fiber_cannot_hide_behind_a_complete_row(unconfirmed_row):
    assert_rejected(f"COTTON 100%\n{unconfirmed_row}")


@pytest.mark.parametrize(
    "row",
    [
        pytest.param("품번 COTTON 50% MODACRYLIC 50%", id="unknown-fiber-with-product-heading"),
        pytest.param("품번 COTTON 50% NYLON", id="unpaired-known-fiber-with-product-heading"),
    ],
)
def test_metadata_word_does_not_hide_unconfirmed_composition(row):
    assert_rejected(f"COTTON 100%\n{row}")


@pytest.mark.parametrize(
    "number_row",
    [
        pytest.param("0.0", id="zero-decimal"),
        pytest.param("-5", id="negative-integer"),
        pytest.param("100.0000000000000000001", id="raw-precision-above-100"),
        pytest.param("100..0", id="malformed-decimal"),
    ],
)
def test_invalid_number_only_row_cannot_be_silently_discarded(number_row):
    assert_rejected(f"COTTON 100%\n{number_row}")


def test_long_numeric_ocr_row_is_a_safe_failure_without_integer_conversion_error():
    # Keep this value out of parametrized IDs and diagnostic output.
    assert_rejected("COTTON 100%\n" + "9" * 5000)


def test_long_numeric_text_returns_material_failure_through_http_service():
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/parse-text", json={"text": "COTTON 100%\n" + "9" * 5000},
        )
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "failed"
    assert body["materials"] == {}
    assert body["error_code"] != "internal_error"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("PU\nLEATHER 100%", id="pu-leather"),
        pytest.param("Faux\nLeather 100%", id="faux-leather"),
        pytest.param("인조\n가죽 100%", id="korean-artificial-leather"),
    ],
)
def test_line_break_does_not_turn_imitation_leather_into_genuine_leather(text):
    assert_rejected(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("LEATHER 100%", {"leather": 100}, id="genuine-leather"),
        pytest.param(
            "STYLE AB123 PU\nLEATHER 100%", {"leather": 100},
            id="product-code-suffix-is-not-an-imitation-modifier",
        ),
        pytest.param(
            "PU\nLINING LEATHER 100%", {"leather": 100},
            id="modifier-does-not-cross-a-new-part-marker",
        ),
        pytest.param("가죽\n100%", {"leather": 100}, id="genuine-stacked-leather"),
        pytest.param("COTTON 100%\nSIZE\n100", {"cotton": 100}, id="explicit-size"),
        pytest.param("COTTON 100% RN 12345", {"cotton": 100}, id="rn-number"),
        pytest.param("품번 AB1234 면 100%", {"cotton": 100}, id="product-code-and-fiber"),
        pytest.param("면 100% 2024년 제조", {"cotton": 100}, id="manufacturing-date"),
        pytest.param(
            "아크릴\n신체치수 가슴둘레\n호칭 95\n95cm\n65%\n레이온\n35%",
            {"acrylic": 65, "rayon": 35},
            id="body-measurement-block-between-composition-rows",
        ),
    ],
)
def test_safety_guards_preserve_genuine_fibers_and_explicit_metadata(text, expected):
    response = analyze_label_text(text)
    assert response["status"] == "success", response
    assert response["materials"] == expected
    assert json.loads(json.dumps(response, allow_nan=False)) == response
    assert parse_materials(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "OUTER COTTON 100%\nLINING UNKNOWN 50%",
            {"cotton": 100},
            id="unknown-lining-does-not-replace-confirmed-outer",
        ),
        pytest.param(
            "OUTER LEATHER 100%\nLINING FAUX\nLEATHER 100%",
            {"leather": 100},
            id="imitation-lining-does-not-negate-genuine-outer",
        ),
    ],
)
def test_problem_in_a_separate_lower_priority_part_does_not_block_confirmed_outer(
    text, expected,
):
    response = analyze_label_text(text)
    assert response["status"] == "success", response
    assert response["selected_part"] == "outer"
    assert response["materials"] == expected
    assert response["parts"]["outer"] == expected
    assert "lining" not in response["parts"]
    assert parse_materials(text) == expected
