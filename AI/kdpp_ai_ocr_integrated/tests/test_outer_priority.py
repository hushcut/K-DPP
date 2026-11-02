"""겉감 미확정은 다른 부위의 완성 조성으로 대체하지 않는다."""

import pytest

from apps.service.label_analysis import analyze_label_text
from apps.text.ocr_text import _assess_candidates, _build_candidate
from apps.text.parse_label import parse_label, parse_parts


@pytest.mark.parametrize("text", [
    "겉감 면 95%\n안감 면 100%",
    "OUTER COTTON 95%\nLINING NYLON 100%",
    "겉감 인조모피\n안감 폴리에스터 100%",
    "OUTER UNKNOWN 100%\nLINING COTTON 100%",
    "OUTER\nLINING COTTON 100%",
    "겉감 면 95%\n배색 면 95% 폴리우레탄 5%",
    "表地 綿 95%\n裏地 ポリエステル 100%",
    "面料 棉 95%\n里料 涤纶 100%",
    "COTTON 95% SHELL\nNYLON 100% LINING",
    "겉감2 면 95%\n안감 폴리에스터 100%",
])
@pytest.mark.parametrize("analyze", [parse_label, analyze_label_text])
def test_observed_incomplete_outer_blocks_other_parts(text, analyze):
    result = analyze(text)
    assert result["status"] == "failed"
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == result["parts"] == {}
    assert not result.get("selected_part")
    assert result["parse_evidence"]["unconfirmed_outer_parts"]


@pytest.mark.parametrize("text,part,materials", [
    ("겉감 면 95% 폴리우레탄 5%\n안감 면 100%", "outer", {"cotton": 95, "polyurethane": 5}),
    ("OUTER COTTON 100%\nLINING OLEFIN 100%", "outer", {"cotton": 100}),
    ("안감 면 100%", "lining", {"cotton": 100}),
    ("충전재 폴리에스터 100%", "filling", {"polyester": 100}),
    ("면 100%", "generic", {"cotton": 100}),
    ("COTTON 100%\n겉감2 POLYESTER 100%", "outer_2", {"polyester": 100}),
])
def test_confirmed_outer_and_labels_without_outer_remain_usable(text, part, materials):
    result = analyze_label_text(text)
    assert result["status"] == "success"
    assert result["selected_part"] == part
    assert result["materials"] == materials


@pytest.mark.parametrize("part", ["outer", "outer_2"])
@pytest.mark.parametrize("metadata", ["conflict", "ratio", "rejection"])
def test_another_candidate_cannot_hide_observed_outer_damage(part, metadata):
    kwargs = {
        "conflict": {"conflicting_parts": (part,)},
        "ratio": {"unpaired_ratio_parts": (part,)},
        "rejection": {"rejected_composition_parts": {part: ("unpaired_material_rows",)}},
    }[metadata]
    result = parse_label("LINING COTTON 100%", **kwargs)
    assert result["status"] == "failed"
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == {}


def test_partial_part_observations_remain_available_without_becoming_primary():
    text = "OUTER COTTON 95%\nLINING NYLON 100%"
    assert parse_parts(text) == {"lining": {"nylon": 100}}
    result = parse_label(text)
    assert result["materials"] == {}
    assert result["parse_evidence"]["paired_material_ratios"]["lining"] == [["nylon", 100.0]]


def test_candidate_selection_retains_outer_failure_across_a_clipped_read():
    source = _build_candidate("original", "OUTER POLYESTER\nLINING COTTON 100%")
    clipped = _build_candidate("preprocessed", "LINING COTTON 100%")
    assert _assess_candidates([source, clipped]).status == "failed"
    restored = _build_candidate("material_crop", "OUTER POLYESTER 100%\nLINING COTTON 100%")
    decision = _assess_candidates([source, clipped, restored])
    assert decision.status == "success"
    assert decision.best.selected_part == "outer"
    assert decision.best.materials == {"polyester": 100}


def test_failed_read_keeps_confirmed_secondary_evidence_without_publishing_it():
    partial = _build_candidate("original", "OUTER COTTON 95%\nLINING NYLON 100%")
    unreadable = _build_candidate("preprocessed", "UNREAD 100%")
    decision = _assess_candidates([partial, unreadable])
    assert decision.status == "failed"
    assert decision.best is partial
    assert decision.best.materials == {}
    assert decision.best.parts == {"lining": {"nylon": 100}}
    assert decision.best.unconfirmed_outer_parts == ("outer",)
