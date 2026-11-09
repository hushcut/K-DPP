"""Keep split washing captions from becoming extra composition ratios."""

import pytest

from apps.text.ocr_candidates import build_candidate, find_unpaired_ratio_parts
from apps.text.parse_label import build_line_infos, parse_label


@pytest.mark.parametrize("temperature", ["30", "40", "50", "60", "70", "95"])
@pytest.mark.parametrize("care", ["HAND WASH", "손세탁", "手洗", "手洗い"])
def test_explicit_complete_content_before_wash_caption_keeps_temperature_out(temperature, care):
    text = f"OUTER\nPOLYESTER 60%\nRAYON 35%\nPOLYURETHANE 5%\n{care}\n{temperature}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 60, "rayon": 35, "polyurethane": 5}
    assert result["selected_part"] == "outer"
    assert result["parse_evidence"]["observed_ratios"] == {"outer": [60.0, 35.0, 5.0]}


@pytest.mark.parametrize("care", [
    "중성\n별도 세탁",
    "중성세제\n손세탁",
    "neutral detergent\nHAND WASH",
    "손세탁\n30\n중성\n별도 세탁",
])
def test_neutral_caption_requires_a_complete_wash_instruction(care):
    # A second temperature is deliberately not introduced by this fixture.
    tail = care if care.startswith("손세탁") else "30\n" + care
    result = parse_label("COTTON 100%\n" + tail)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}


@pytest.mark.parametrize("prefix", [
    "COTTON 70%\nSPANDEX",
    "COTTON 100",
    "COTTON 100%\nUNKNOWN",
    "COTTON 100%\nNYLON",
    "COTTON 100%\nCOMPOSITION",
    "OUTER COTTON 100%\nLINING",
    "OUTER COTTON 100%\nOUTER",
    "COTTON 100%\nSIZE M",
])
def test_temperature_cannot_borrow_a_distant_or_incomplete_composition(prefix):
    infos = build_line_infos(prefix + "\nHAND WASH\n30")
    assert not infos[-1].is_metadata
    assert infos[-1].numbers == (30,)


@pytest.mark.parametrize("care", [
    "HAND WASH ?", "HAND WASH？", "HAND WASH UNKNOWN", "HAND WASH OLEFIN",
    "HAND WASH 20%", "HAND WASH ±", "DO NOT BLEACH", "IRON", "DRY CLEAN",
])
def test_opaque_numeric_or_nonwashing_caption_cannot_hide_a_ratio(care):
    infos = build_line_infos(f"COTTON 100%\n{care}\n30")
    assert not infos[-1].is_metadata


@pytest.mark.parametrize("tail", [
    "30\n40", "30\n10%", "30\nUNKNOWN\nHAND WASH", "30\n중성",
    "30\n중성\nUNKNOWN\n별도 세탁", "30\n중성\n80-120\n별도 세탁",
])
def test_split_care_does_not_skip_numeric_or_unknown_rows(tail):
    infos = build_line_infos("COTTON 100%\n" + tail)
    temperature = next(info for info in infos if info.normalized == "30")
    assert not temperature.is_metadata


@pytest.mark.parametrize("number", ["30%", "-30", "30.5", "300", "30?", "30≈"])
def test_only_a_literal_supported_temperature_can_be_excluded(number):
    infos = build_line_infos(f"COTTON 100%\nHAND WASH\n{number}")
    assert not infos[-1].inferred_metadata


def test_split_wash_caption_does_not_poison_other_ocr_candidates():
    candidates = [
        build_candidate("original", "COTTON 100%\nHAND WASH\n30", parse_candidate=parse_label),
        build_candidate("original", "COTTON 100%\nHAND WASH 30", parse_candidate=parse_label, layout_used=True),
    ]
    assert all(candidate.parser_status == "success" for candidate in candidates)
    assert find_unpaired_ratio_parts(candidates) == ()


def test_new_care_context_does_not_discard_an_extra_material():
    result = parse_label("COTTON 100%\nHAND WASH\n30\nOLEFIN 10%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("tail", [
    "30\n40\nHAND WASH", "40\n30\nHAND WASH", "30\n40%\nHAND WASH",
    "30\nUNKNOWN", "30\n?", "30\n中",
])
def test_existing_metadata_cannot_hide_a_second_number_or_opaque_following_row(tail):
    infos = build_line_infos("COTTON 100%\nHAND WASH\n" + tail)
    first = infos[2]
    assert not first.is_metadata
