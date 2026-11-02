"""Public guidance must describe the final composition without changing its decision."""

from copy import deepcopy

import pytest

from apps.service import label_analysis
from apps.service.response_contract import normalize_label_response
from apps.text.ocr_text import OcrAttempt, OcrMetadata, OcrResult
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("part,public_part", [
    ("outer", "outer"), ("outer_2", "outer_2"),
    ("generic", "unidentified"), ("lining", "lining"),
    ("filling", "filling"), ("pocket", "pocket"), ("rib", "rib"),
    ("sleeve", "sleeve"), ("color_block", "color_block"),
    ("embroidery_yarn", "embroidery_yarn"),
])
def test_public_part_codes_follow_the_selected_composition(part, public_part):
    parsed = normalize_label_response({
        "status": "success", "materials": {"cotton": 100},
        "selected_part": part, "parts": {part: {"cotton": 100}},
        "warnings": ["existing_diagnostic"],
    }, api_version="1.0")
    before = deepcopy(parsed)
    result = label_analysis._with_public_guidance(parsed)

    assert result["warnings"] == ["existing_diagnostic", f"composition_part:{public_part}"]
    assert {k: v for k, v in result.items() if k != "warnings"} == {
        k: v for k, v in before.items() if k != "warnings"
    }
    assert parsed == before


@pytest.mark.parametrize("text,code", [
    ("OUTER COTTON 100%", "composition_part:outer"),
    ("LINING POLYESTER 100%", "composition_part:lining"),
    ("COTTON 80% POLYESTER 20%", "composition_part:unidentified"),
])
def test_text_analysis_exposes_selected_part(text, code):
    baseline = normalize_label_response(parse_label(text), api_version="1.0")
    result = label_analysis.analyze_label_text(text)

    assert result["warnings"] == [*baseline["warnings"], code]
    for field in ("status", "materials", "parts", "selected_part", "error_code"):
        assert result[field] == baseline[field]


def test_reserved_guidance_is_rebuilt_without_duplicates_or_input_mutation():
    parsed = normalize_label_response({
        "status": "success", "materials": {"cotton": 100},
        "selected_part": "outer", "parts": {"outer": {"cotton": 100}},
        "warnings": [
            "existing_diagnostic", "composition_part:lining", "composition_part:outer",
            "composition_action:retake_composition_region", "other_diagnostic",
        ],
    }, api_version="1.0")
    before = deepcopy(parsed)
    result = label_analysis._with_public_guidance(parsed)

    assert result["warnings"] == [
        "existing_diagnostic", "other_diagnostic", "composition_part:outer",
    ]
    assert label_analysis._with_public_guidance(result) == result
    assert parsed == before


def test_unregistered_successful_part_is_publicly_unidentified():
    parsed = normalize_label_response({
        "status": "success", "materials": {"cotton": 100},
        "selected_part": "unregistered_internal_part",
        "parts": {"unregistered_internal_part": {"cotton": 100}},
    }, api_version="1.0")
    result = label_analysis._with_public_guidance(parsed)

    assert result["warnings"] == ["composition_part:unidentified"]
    assert result["selected_part"] == "unregistered_internal_part"


def test_failed_confirmed_lining_never_becomes_a_public_success_part():
    parsed = normalize_label_response({
        "status": "failed", "error_code": "incomplete_part_composition",
        "warnings": ["existing_diagnostic", "composition_part:lining"],
        "parse_evidence": {"confirmed_parts": {"lining": {"polyester": 100}}},
    }, api_version="1.0")
    result = label_analysis._with_public_guidance(parsed)

    assert result["warnings"] == ["existing_diagnostic"]
    assert result["materials"] == result["parts"] == {}
    assert result["selected_part"] == ""


def test_completed_ocr_with_incomplete_outer_exposes_only_recapture_action():
    source = OcrResult("OUTER COTTON 95%\nLINING POLYESTER 100%", OcrMetadata(
        source="original", confidence="medium", candidate_count=1,
        image_format="JPEG", width=4, height=4,
        attempts=(OcrAttempt("original", "success", 0, False),), attempt_count=1,
    ))
    result = label_analysis.analyze_ocr_result(source)

    assert result["status"] == "failed"
    assert result["materials"] == result["parts"] == {}
    assert result["selected_part"] == ""
    assert result["parse_evidence"]["recapture"]["action"] == "retake_composition_region"
    public = [warning for warning in result["warnings"]
              if warning.startswith(("composition_part:", "composition_action:"))]
    assert public == ["composition_action:retake_composition_region"]
