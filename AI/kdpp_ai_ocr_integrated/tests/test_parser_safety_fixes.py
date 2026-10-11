"""Behavioral regressions for care, ratio precision and safe public parsing."""

import pytest

from apps.text.parse_label import (
    normalize_percentages,
    parse_care,
    parse_label,
    parse_materials,
)
from apps.text.qa_dataset import parse_answer_materials
from part_policy_assertions import assert_selected_part


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DO NOT MACHINE WASH", {"기계세탁 금지"}),
        ("DO NOT HAND WASH", {"손세탁 금지"}),
        ("DO NOT\nMACHINE WASH COLD", {"기계세탁 금지"}),
        ("DON'T HAND WASH", {"손세탁 금지"}),
        ("기계세탁 금지; 손세탁", {"기계세탁 금지", "손세탁"}),
        ("손세탁 금지; 기계세탁", {"손세탁 금지", "기계세탁"}),
        ("HAND WASH COLD", {"찬물 손세탁"}),
        ("COLD HAND WASH", {"찬물 손세탁"}),
        ("HAND WASH WARM", {"미온수 손세탁"}),
        ("찬물 손세탁", {"찬물 손세탁"}),
        ("WASH COLD", {"찬물 세탁"}),
        ("미온수 세탁", {"미온수 세탁"}),
        ("MACHINE WASH COLD", {"찬물 기계세탁"}),
        ("DO NOT WASH; HAND WASH COLD", {"물세탁 금지"}),
        ("DO NOT BLEACH; MACHINE WASH COLD", {"표백 금지", "찬물 기계세탁"}),
        ("DO NOT TUMBLE DRY LOW", {"건조기 사용 금지"}),
        ("DO NOT DRYCLEAN", {"드라이클리닝 금지"}),
        ("NOT MACHINE WASH", set()),
    ],
)
def test_care_preserves_method_temperature_and_negation(text, expected):
    assert set(filter(None, parse_care(text).split("; "))) == expected


def test_decimal_ratios_keep_input_precision_in_output_and_answer_key():
    expected = {"cotton": 33.33, "polyester": 33.33, "wool": 33.34}
    result = parse_label("COTTON 33.33% POLYESTER 33.33% WOOL 33.34%")
    assert result["status"] == "success"
    assert result["materials"] == expected
    assert sum(result["materials"].values()) == pytest.approx(100)
    assert "33.34%" in result["materials_korean"]
    assert normalize_percentages(expected) == expected
    assert parse_answer_materials(
        {"answer_materials": "cotton;polyester;wool", "answer_ratios": "33.33;33.33;33.34"},
        row_number=2,
    ) == expected


@pytest.mark.parametrize(
    "text",
    [
        "COTTON -100%", "COTTON −100%", "COTTON -100",
        "COTTON 100%\n120%", "COTTON 100%\n1000%", "COTTON 100%\n0%",
        "COTTON 100%\n-20%", "COTTON 100% 120%", "COTTON 100 120",
        "OUTER\n120%\nLINING POLYESTER 100%",
        "OUTER COTTON -80%\nLINING POLYESTER 100%",
    ],
)
def test_invalid_ratios_cannot_be_discarded_to_confirm_composition(text):
    result = parse_label(text)
    if "LINING" in text:
        assert_selected_part(result, 'lining', {'polyester': 100}, unconfirmed='outer')
        return
    assert parse_label(text)["status"] == "failed"
    assert parse_materials(text) == {}


@pytest.mark.parametrize(
    "text",
    [
        "COTTON - 100%", "COTTON: 100%", "COTTON 100% MADE IN 2025",
        "COTTON 100%\nMACHINE WASH 30°C", "COTTON 100% (TRIM NYLON 120%)",
        "OUTER COTTON 100%\nLINING POLYESTER 120%",
        "COTTON 100%\n500", "COTTON 100%\n0",
    ],
)
def test_ratio_guard_preserves_separators_metadata_and_separate_parts(text):
    assert parse_label(text)["materials"] == {"cotton": 100}


@pytest.mark.parametrize(
    "text",
    ["面料:55%棉,45%聚酯纤维", "面料:55%棉,45%聚酯纖維", "COTTON 55,POLYESTER 45%"],
)
def test_comma_between_materials_remains_a_separator(text):
    assert parse_label(text)["materials"] == {"cotton": 55, "polyester": 45}


@pytest.mark.parametrize(
    "text",
    [
        "OUTER COTTON 80%\nLINING POLYESTER 100%",
        "COTTON 80%\nLINING POLYESTER 100%",
        "OUTER\nLINING POLYESTER 100%",
        "COTTON 100%\nPOLYESTER 100%",
        "", "COTTON 80% POLYESTER 20%",
        "OUTER COTTON 100%\nLINING POLYESTER 100%",
    ],
)
def test_materials_entrypoint_shares_label_safety_policy(text):
    assert parse_materials(text) == parse_label(text)["materials"]
