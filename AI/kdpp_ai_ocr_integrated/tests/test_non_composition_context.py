"""품번·보관 문구·세탁기호를 혼용률 근거와 구분하는 회귀 검사."""

import pytest

from apps.text.ocr_candidates import build_candidate, find_rejected_composition_parts
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("code", [
    "341-404149", "341-404149082-35)", "1800-9710", "080-481-2950",
    "341 - 404149082 - 35 )", "( 080 - 481 - 2950 )",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_numeric_product_and_contact_rows_do_not_reject_composition(code, placement):
    text = f"{code}\nCOTTON 100%" if placement == "before" else f"COTTON 100%\n{code}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}


@pytest.mark.parametrize("storage", [
    "FOLD DOWN", "FORD DOWN", "DRY FOLD DOWN AVOID DIRECT",
    "CLEANING DRY FOR FORD DOWN AVOID DIRECT",
])
def test_storage_action_is_not_down_filling(storage):
    result = parse_label(f"COTTON 100%\n{storage}")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_materials"] == {"generic": ["cotton"]}


def test_storage_action_on_composition_row_keeps_explicit_materials():
    result = parse_label("COTTON 100% FOLD DOWN")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}


@pytest.mark.parametrize("glyph", ["130/", "140/", "160/", "195/", "130 /", "140 \\"])
def test_wash_glyph_after_explicit_material_row_is_not_a_ratio(glyph):
    result = parse_label(f"M\n95% Polyester\n5% Elastane\n{glyph}\nMADE IN CHINA")
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 95, "spandex": 5}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [95.0, 5.0]}


@pytest.mark.parametrize("text", [
    "COTTON 100%\nCOMPOSITION\n130/",
    "COTTON 100%\nCOTTON 130/",
    "COTTON 100%\n130%",
    "COTTON 100%\n130/%",
    "COTTON 100%\n30/",
    "COTTON 100%\n40-60",
    "COTTON 100%\n341-404149 OLEFIN 10%",
    "COTTON 100%\n1800-9710 POLYESTER 10%",
    "COTTON 100%\nFOLD DOWN OLEFIN 10%",
    "COTTON 90%\nFOLD DOWN 10%",
    "COTTON 100%\nFOLD DOWN 10%",
    "COTTON 100%\nCOTTON -5%",
])
def test_noncomposition_detection_cannot_hide_ratio_or_material_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_ignored_code_cannot_join_material_to_unrelated_ratio():
    result = parse_label("COTTON\n341-404149\n100%\nPOLYESTER 100%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("text, expected", [
    ("DOWN 100%", {"down": 100}),
    ("FILLING DOWN 90% FEATHER 10%", {"down": 90, "feather": 10}),
])
def test_real_down_composition_is_preserved(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("noise", [
    "341-404149082-35)", "FOLD DOWN", "130/", "341-404149082-35 )", "130 /",
])
def test_noncomposition_noise_does_not_poison_ocr_candidate_evidence(noise):
    candidates = [
        build_candidate("original", f"COTTON 100%\n{noise}", parse_candidate=parse_label),
        build_candidate("original", "COTTON 100%", parse_candidate=parse_label, layout_used=True),
    ]
    assert all(c.parser_status == "success" for c in candidates)
    assert find_rejected_composition_parts(candidates, selected_part="generic") == {}


@pytest.mark.parametrize("temperature", ["30", "40", "60", "95"])
@pytest.mark.parametrize("care", ["HAND WASH", "손세탁"])
def test_wash_tub_temperature_next_to_care_text_is_not_an_orphan_ratio(temperature, care):
    result = parse_label(f"COTTON 100%\n{temperature}\n{care}")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}


@pytest.mark.parametrize("text", [
    "COTTON 70%\n30\nHAND WASH",
    "COTTON 100%\nCOMPOSITION\n30\nHAND WASH",
    "COTTON 100%\n30%\nHAND WASH",
    "COTTON 100%\n30\nPOLYESTER",
    "COTTON 100%\n30\nHAND WASH OLEFIN 10%",
])
def test_wash_context_cannot_erase_composition_numbers_or_unknown_fibers(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("care", [
    "NEUTRAL\nDETERGENT\nHAND WASH",
    "NEUTRAL\nDETERGENT HAND WASH SEPARATENESS",
])
def test_wash_temperature_before_split_neutral_detergent_care_is_not_a_ratio(care):
    result = parse_label(f"COTTON 95% SPANDEX 5%\n30\n{care}")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 95, "spandex": 5}


@pytest.mark.parametrize("text", [
    "COTTON 70%\n30\nNEUTRAL\nDETERGENT\nHAND WASH",
    "COTTON 100%\nCOMPOSITION\n30\nNEUTRAL\nDETERGENT\nHAND WASH",
    "COTTON 100%\n30%\nNEUTRAL\nDETERGENT\nHAND WASH",
    "COTTON 100%\n30\nNEUTRAL\nDETERGENT HAND WASH OLEFIN 10%",
    "COTTON 100%\n30\nNEUTRAL\nDETERGENT",
])
def test_split_detergent_context_cannot_hide_composition_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
