import pytest

from apps.service.label_analysis import analyze_label_text
from apps.text.material_extraction import extract_materials
from apps.text.parse_label import parse_label
from apps.text.scoped_materials import read_yarn_materials
from apps.text.ocr_text import OcrMetadata, OcrResult
from apps.service.label_analysis import analyze_ocr_result


@pytest.mark.parametrize("text", ["POLY 100%", "100% POLY", "poly 100%", "POLY 60% COTTON 40%"])
def test_explicitly_confirmed_poly_abbreviation(text):
    result = analyze_label_text(text, confirmed_polyester_poly=True)
    assert result["status"] == "success"
    assert result["materials"] == ({"polyester": 60, "cotton": 40} if "60" in text else {"polyester": 100})
    assert "poly_abbreviation_as_polyester" in result["warnings"]
    assert result["confidence"]["parser"] == "medium"


@pytest.mark.parametrize("text", ["POLYPROPYLENE 100%", "POLYAMIDE 100%", "POLYURETHANE 100%", "POLYGON", "POLYMER"])
def test_poly_is_not_a_prefix_alias(text):
    assert "polyester" not in extract_materials(text)


@pytest.mark.parametrize("text", ["POLY 95% OLEFIN 5%", "POLY 95%", "POLY 100% UNKNOWN 5%", "POLY 1100%"])
def test_abbreviation_does_not_relax_ratio_or_unknown_fiber_policy(text):
    assert parse_label(text, confirmed_polyester_poly=True)["status"] == "failed"


def test_yarn_country_clauses_are_auxiliary_not_shell_materials():
    text = "BRODERI\nYARN/FIL/GARN\nUK: 100% POLYESTER FR: 100% POLYESTER\nJP: 100% 未読\nKR: 100% 폴리에스터"
    result = analyze_label_text(text)
    observed = result["parse_evidence"]["scoped_materials"]
    assert observed["scope"] == "embroidery_yarn"
    assert observed["materials"] == {"polyester": 100}
    assert observed["status"] == "partial"
    assert len(observed["unconfirmed_clauses"]) == 1
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert not observed["is_primary_composition"]


def test_complete_yarn_clause_keeps_scope():
    result = analyze_label_text("EMBROIDERY YARN: 100% POLYESTER")
    assert result["status"] == "success"
    assert result["selected_part"] == "embroidery_yarn"
    assert result["materials"] == {"polyester": 100}
    assert result["parse_evidence"]["scoped_materials"]["materials"] == {"polyester": 100}


def test_conflicting_language_clauses_do_not_choose_polyester():
    result = read_yarn_materials("YARN/\nUK: 100% POLYESTER FR: 100% COTTON")
    assert result["status"] == "conflicting"
    assert result["materials"] == {}
    assert len(result["observations"]) == 2


@pytest.mark.parametrize("text", ["POLYESTER 100%", "YARN COMPANY\nUK: 100% POLYESTER", "YARN/\nUK: 95% POLYESTER", "YARN/\nUK: 100% POLYESTER OLEFIN", "YARN/\nUK: 100% UNKNOWN", "COTTON 100%\nYARN/\nUK: 100% POLYESTER", "YARN/\nUK: 100% +POLYESTER", "YARN/\nUK: 100% POLYESTER-", "YARN/\nUK: 100% <POLYESTER>"])
def test_auxiliary_extraction_requires_exact_scope_and_complete_clause(text):
    assert read_yarn_materials(text) is None


@pytest.mark.parametrize("text", ["Adorable 40%\nChic 30%\nDream 30%", "OUTER 천연가죽(양가죽)", "YARN POLYESTER 95%"])
def test_other_special_label_policies_remain_safe(text):
    result = parse_label(text)
    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_full_image_yarn_scope_survives_selection_of_a_crop_without_its_heading():
    scoped = read_yarn_materials("BRODERI\nYARN/\nUK: 100% POLYESTER JP: 100% 未読")
    ocr = OcrResult("UK: 100% POLYESTER JP: 100% 未読", OcrMetadata(
        source="material_crop", confidence="low", candidate_count=2,
        image_format="JPEG", width=800, height=600, scoped_materials=scoped,
    ))
    result = analyze_ocr_result(ocr)
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert result["parse_evidence"]["scoped_materials"]["materials"] == {"polyester": 100}
    assert "yarn_materials_are_not_primary_composition" in result["warnings"]
    result["parse_evidence"]["scoped_materials"]["materials"]["polyester"] = 1
    assert ocr.metadata.scoped_materials["materials"] == {"polyester": 100}
