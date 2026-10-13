"""Material confirmation, unknown parts and explicit review stay distinct."""

from dataclasses import replace

import pytest

from apps.service.label_analysis import (
    analyze_label_text, analyze_ocr_result, get_ocr_review_options,
)
from apps.service.response_contract import LabelResponseContract
from apps.text import ocr_text
from apps.text.parse_label import parse_label


PART_WARNING = "representative_part_unidentified:generic"
REVIEW_WARNING = "manual_composition_review_required:first_generic"
MULTIPLE = "MATERIAL\nRAYON 45%\nNYLON 28%\nPOLYESTER 22%\nPOLYURETHANE 5%\nCUSTOMFIBER 60%\nPOLYESTER 40%"


def ocr_result(text, *, original_text=None):
    original = replace(ocr_text._build_candidate("original", original_text or text),
                       image_key="a" * 64, image_variant_key="b" * 64)
    return ocr_text.OcrResult(text, ocr_text.OcrMetadata(
        source="original", confidence="medium", candidate_count=1,
        image_format="JPEG", width=800, height=1200,
    ), original_candidate=original)


@pytest.mark.parametrize("text", ["면 100%", "COTTON 95% SPANDEX 5%", "綿 100%"])
@pytest.mark.parametrize("ocr", [False, True])
def test_confirmed_materials_do_not_acquire_an_outer_part(text, ocr):
    before = parse_label(text)
    result = analyze_ocr_result(ocr_result(text)) if ocr else analyze_label_text(text)
    assert result["status"] == "success"
    assert result["selected_part"] == "generic"
    assert result["materials"] == before["materials"] == result["parts"]["generic"]
    assert result["parts"] == before["parts"]
    assert result["confidence"]["parser"] == before["confidence"]["parser"]
    assert PART_WARNING in result["warnings"]
    assert PART_WARNING not in before["warnings"]  # Candidate scoring is unchanged.
    assert REVIEW_WARNING not in result["warnings"]


@pytest.mark.parametrize("text,part", [
    ("OUTER COTTON 100%", "outer"),
    ("OUTER UNKNOWN 100%\nLINING POLYESTER 100%", "lining"),
    ("YARN POLYESTER 100%", "embroidery_yarn"),
])
def test_an_explicit_part_or_fallback_keeps_its_existing_meaning(text, part):
    result = analyze_ocr_result(ocr_result(text))
    assert result["status"] == "success" and result["selected_part"] == part
    assert PART_WARNING not in result["warnings"]
    assert REVIEW_WARNING not in result["warnings"]
    assert "review" not in result["parse_evidence"]


def test_available_review_never_populates_the_automatic_failure():
    source = ocr_result("UNREAD 100%", original_text=MULTIPLE)
    before = analyze_ocr_result(replace(source, original_candidate=None))
    automatic = analyze_ocr_result(source)
    option = get_ocr_review_options(source)[0]
    assert automatic["status"] == "failed"
    assert automatic["materials"] == automatic["parts"] == {}
    assert automatic["selected_part"] == ""
    assert automatic["error_code"] == before["error_code"]
    assert automatic["ocr"] == before["ocr"]
    assert PART_WARNING not in automatic["warnings"]
    assert REVIEW_WARNING in automatic["warnings"]
    evidence = automatic["parse_evidence"]["review"]
    assert evidence["confirmed"] is False and evidence["confirmation_required"] is True
    assert evidence["option_id"] == option["id"]
    assert evidence["selected_part"] == option["selected_part"] == "generic"
    assert evidence["confirmation_scope"] == "materials_and_ratios"
    LabelResponseContract.model_validate(automatic)

    reviewed = analyze_ocr_result(source, confirmed_review_id=option["id"])
    assert reviewed["status"] == "success"
    assert reviewed["materials"] == option["materials"]
    assert reviewed["selected_part"] == "generic" and PART_WARNING in reviewed["warnings"]
    assert REVIEW_WARNING not in reviewed["warnings"]
    assert reviewed["parse_evidence"]["review"]["confirmed"] is True
    assert REVIEW_WARNING in reviewed["parse_evidence"]["review"]["automatic_warnings"]
    reviewed["parse_evidence"]["review"]["automatic_warnings"].append("changed")
    automatic["parse_evidence"]["review"]["confirmed"] = True
    assert analyze_ocr_result(source)["parse_evidence"]["review"]["confirmed"] is False


@pytest.mark.parametrize("text", [
    "COTTON 100%",
    "COTTON 99%\nCUSTOMFIBER 60%\nPOLYESTER 40%",
    "CUSTOMFIBER 100%\nCOTTON 60%\nPOLYESTER 40%",
    "OUTER COTTON 100%\nLINING POLYESTER 100%",
])
def test_a_complete_first_block_is_still_required_for_review(text):
    source = ocr_result("UNREAD 100%", original_text=text)
    automatic = analyze_ocr_result(source)
    assert automatic["status"] == "failed"
    assert REVIEW_WARNING not in automatic["warnings"]
    assert "review" not in automatic["parse_evidence"]
    assert get_ocr_review_options(source) == []


@pytest.mark.parametrize("change", ["missing", "crop", "layout", "photo"])
def test_review_guidance_requires_the_identified_literal_original(change):
    source = ocr_result("UNREAD 100%", original_text=MULTIPLE)
    original = source.original_candidate
    if change == "missing":
        original = None
    else:
        original = replace(original, **{
            "crop": {"source": "material_crop"},
            "layout": {"layout_used": True},
            "photo": {"image_key": ""},
        }[change])
    result = analyze_ocr_result(replace(source, original_candidate=original))
    assert REVIEW_WARNING not in result["warnings"]
    assert "review" not in result["parse_evidence"]


def test_part_guidance_is_not_duplicated_by_ocr_metadata():
    source = ocr_result("COTTON 100%")
    source = replace(source, metadata=replace(source.metadata, warnings=(PART_WARNING,)))
    assert analyze_ocr_result(source)["warnings"].count(PART_WARNING) == 1


def test_text_only_confirmation_does_not_invent_a_photo_review_id():
    result = analyze_label_text(MULTIPLE, confirmed_first_generic=True)
    assert result["status"] == "success" and result["selected_part"] == "generic"
    assert PART_WARNING in result["warnings"]
    assert "review" not in result["parse_evidence"]
