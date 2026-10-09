"""Peer outer panels need one agreed composition before exposing a primary."""

import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text.ocr_text import OcrMetadata, OcrResult, _assess_candidates, _build_candidate
from apps.text.parse_label import parse_label, parse_materials, parse_parts


@pytest.mark.parametrize("first,second", [
    ("OUTSHELL1", "OUTSHELL2"), ("OUTER 1", "OUTER 2"),
    ("겉감1", "겉감2"), ("CUTSHELL", "OUTSHELL2"),
])
@pytest.mark.parametrize("reverse", [False, True])
def test_different_complete_outer_panels_have_no_automatic_primary(first, second, reverse):
    rows = [f"{first} Cotton 100%", f"{second} Cotton 70% Polyester 30%"]
    text = "\n".join(reversed(rows) if reverse else rows)
    result = parse_label(text)
    assert result["status"] == "failed"
    assert result["error_code"] == "ambiguous_composition"
    assert result["materials"] == result["parts"] == {}
    assert parse_materials(text) == {}
    assert parse_parts(text) == {"outer": {"cotton": 100}, "outer_2": {"cotton": 70, "polyester": 30}}
    assert result["parse_evidence"]["paired_material_ratios"]["outer_2"] == [["cotton", 70.0], ["polyester", 30.0]]
    assert result["parse_evidence"]["rejected_composition_parts"] == {
        "outer": ["ambiguous_outer_compositions"],
        "outer_2": ["ambiguous_outer_compositions"],
    }


@pytest.mark.parametrize("secondary", [
    "OUTSHELL2", "OUTSHELL2 Polyester", "OUTSHELL2 Polyester 90%",
    "OUTSHELL2 UNKNOWN 100%", "OUTSHELL2 Polyester -100%",
    "OUTSHELL2 Cotton 70% Polyester 30%\n8.",
    "OUTSHELL2 Cotton 70% Polyester 30%\nOUTSHELL2 Nylon 100%",
])
def test_unconfirmed_peer_outer_is_not_ignored_for_a_complete_first_panel(secondary):
    text = "OUTSHELL1 Cotton 100%\n" + secondary
    result = parse_label(text)
    assert result["status"] == "failed"
    assert result["materials"] == result["parts"] == {}
    assert parse_parts(text)["outer"] == {"cotton": 100}
    assert "outer_2:composition_not_confirmed" in result["warnings"]


@pytest.mark.parametrize("first,second,expected", [
    ("Cotton 100%", "Cotton 100%", {"cotton": 100}),
    ("Cotton 100%", "Coton 100%", {"cotton": 100}),
    ("Cotton 70% Polyester 30%", "Cotton 70% Polyester 30%", {"cotton": 70, "polyester": 30}),
    ("Cotton 99.5% Spandex 0.5%", "Cotton 99.5% Elastane 0.5%", {"cotton": 99.5, "spandex": 0.5}),
    ("Polyester 100%", "Poliéster 100%", {"polyester": 100}),
])
def test_complete_equivalent_peer_panels_remain_confirmed(first, second, expected):
    result = parse_label(f"OUTSHELL1 {first}\nOUTSHELL2 {second}")
    assert result["status"] == "success"
    assert result["materials"] == expected
    assert result["selected_part"] == "outer"
    assert set(result["parts"]) == {"outer", "outer_2"}


@pytest.mark.parametrize("suffix", [
    "", "LINING UNKNOWN 100%", "FILLING Polyester", "POCKET Nylon 90%",
    "RIB Cotton 80%\nRIB Nylon 100%", "CONTRAST UNKNOWN 100%",
])
def test_single_outer_keeps_independent_lower_priority_failures(suffix):
    result = parse_label("OUTSHELL1 Cotton 100%\n" + suffix)
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"


@pytest.mark.parametrize("secondary", [
    "OUTSHELL2 Cotton 70% Polyester 30%",
    "OUTSHELL2 Cotton 70% Polyester 30%\n8.",
    "OUTSHELL2 Polyester",
])
def test_a_crop_cannot_erase_the_other_outer_panel(secondary):
    whole = _build_candidate("original", "OUTSHELL1 Cotton 100%\n" + secondary)
    crop = _build_candidate("material_crop", "OUTSHELL1 Cotton 100%")
    decision = _assess_candidates([whole, crop])
    assert decision.status == "failed"
    metadata = OcrMetadata(
        "material_crop", "low", 2, "JPEG", 100, 100,
        conflicting_parts=decision.conflicting_parts,
        unpaired_ratio_parts=decision.unpaired_ratio_parts,
        rejected_composition_parts=decision.rejected_composition_parts,
    )
    response = analyze_ocr_result(OcrResult(decision.best.text, metadata))
    assert response["status"] == "failed"
    assert response["materials"] == response["parts"] == {}


def test_equal_panels_can_recover_a_missing_primary_ratio():
    raw = _build_candidate("original", "OUTSHELL1 Polyester\nOUTSHELL2 Polyester 100%")
    complete = _build_candidate("preprocessed", "OUTSHELL1 Polyester 100%\nOUTSHELL2 Polyester 100%")
    decision = _assess_candidates([raw, complete])
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 100}
    assert not decision.rejected_composition_parts


def test_an_unread_peer_outer_does_not_bound_a_representative_restored_panel():
    text = (
        "OUTSHELL1\nCOTTON 60% /\nCOTON / ALGODÓN\n"
        "POLYESTER 40% /\nPOLIÉSTER / ポリエステル\nOUTSHELL2\nUNKNOWN"
    )
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == result["parts"] == {}
    assert parse_parts(text) == {"outer": {"cotton": 60, "polyester": 40}}
    assert "outer_2:composition_not_confirmed" in result["warnings"]


@pytest.mark.parametrize("constraint", [
    {"unpaired_ratio_parts": ("outer_2",)},
    {"conflicting_parts": ("outer_2",)},
    {"rejected_composition_parts": {"outer_2": ("unpaired_material_rows",)}},
])
def test_peer_evidence_from_other_candidates_also_blocks_single_panel(constraint):
    result = parse_label("OUTSHELL1 Cotton 100%", **constraint)
    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize("constraint", [
    {"unpaired_ratio_parts": ("lining",)},
    {"conflicting_parts": ("filling",)},
    {"rejected_composition_parts": {"pocket": ("unpaired_material_rows",)}},
])
def test_other_part_constraints_do_not_become_peer_outer_constraints(constraint):
    result = parse_label("OUTSHELL1 Cotton 100%", **constraint)
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
