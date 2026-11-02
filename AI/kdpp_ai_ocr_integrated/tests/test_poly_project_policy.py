"""POLY is a project alias; complete fiber names and rejection evidence stay intact."""

from io import BytesIO

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_label_text, analyze_ocr_result
from apps.text import ocr_text
from apps.text.material_extraction import extract_materials
from apps.text.parse_label import parse_label
from scripts.track_ocr_failures import track_failures


@pytest.mark.parametrize("text", [
    "POLY 100%", "100% POLY", "POLY100%", "100%POLY", "poly 100％",
    "ＰＯＬＹ １００％", "OUTER: POLY 100%", "SHELL\nPOLY 100%",
])
def test_complete_poly_composition_is_automatic_with_policy_warning(text):
    result = analyze_label_text(text)
    assert result["status"] == "success"
    assert result["materials"] == {"polyester": 100}
    assert result["confidence"]["parser"] == "medium"
    assert "project_material_alias:poly:polyester" in result["warnings"]
    assert "confirmed_material_alias:poly:polyester" not in result["warnings"]


@pytest.mark.parametrize("text", ["POLY 60% COTTON 40%", "POLY60%\nCOTTON40%"])
def test_poly_mixture_requires_complete_literal_ratios(text):
    assert parse_label(text)["materials"] == {"polyester": 60, "cotton": 40}


@pytest.mark.parametrize("text,expected", [
    ("POLYAMIDE 100%", "nylon"), ("POLYURETHANE 100%", "polyurethane"),
    ("POLY\nAMIDE 100%", "nylon"), ("POLY\nURETHANE 100%", "polyurethane"),
    ("POLY\nESTER 100%", "polyester"),
])
def test_complete_wrapped_fiber_name_does_not_become_poly_abbreviation(text, expected):
    result = parse_label(text)
    assert result["materials"] == {expected: 100}
    assert "project_material_alias:poly:polyester" not in result["warnings"]


@pytest.mark.parametrize("text", [
    "POLYPROPYLENE 100%", "POLYMODACRYLIC 100%", "POLYGON 100%", "POLYMER 100%",
])
def test_poly_does_not_match_prefix_of_unknown_fiber(text):
    assert "polyester" not in extract_materials(text)
    assert parse_label(text)["status"] == "failed"


@pytest.mark.parametrize("text", [
    "POLY -100%", "POLY 99%", "POLY 101%", "POLY", "POLY 100% UNKNOWN 5%",
    "POLY 95% OLEFIN 5%", "FAUX POLY100%", "POLY 1100%", "POLY 100%\n5%",
    "POLY 50% COTTON", "P O L Y 100%", "POLY 100%\nNYLON 100%",
])
def test_policy_never_repairs_unknown_names_numbers_or_competing_compositions(text):
    assert parse_label(text)["status"] == "failed"


def test_existing_candidate_rejection_is_not_erased_by_poly_policy():
    source = ocr_text.OcrResult("POLY100%", ocr_text.OcrMetadata(
        source="original", confidence="low", candidate_count=2,
        image_format="JPEG", width=800, height=1200,
        rejected_composition_parts={"generic": ("unresolved_material_token",)},
    ))
    assert analyze_ocr_result(source)["status"] == "failed"


def test_automatic_policy_is_accepted_by_failure_tracking_without_human_confirmation():
    result = analyze_label_text("POLY 100%")
    report = track_failures([{
        "image_id": "QA001", "sha256": "a" * 64, "source_group": "QA001",
        "included": True, "answer": {"polyester": 100}, "answer_part": "generic",
        "result": result,
    }])
    assert report["summary"]["material_exact"] == 1


def test_normal_ocr_pipeline_applies_poly_policy_without_confirmation(monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (800, 1200), "white").save(buffer, format="PNG")
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_a, **_k: object())
    monkeypatch.setattr(ocr_text, "_run_google_ocr", lambda *_a, **_k: "POLY100%")
    source = ocr_text.run_ocr_bytes(buffer.getvalue(), enable_reflection=False,
        enable_denoised=False, enable_rotated=False, enable_material_region=False)
    result = analyze_ocr_result(source)
    assert result["status"] == "success" and result["materials"] == {"polyester": 100}
    assert "project_material_alias:poly:polyester" in result["warnings"]
