"""Conflicting complete declarations cannot be resolved by layout scores."""

import pytest

from apps.text.parse_label import parse_label, parse_materials


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 100%\nPOLYESTER 80% WOOL 20%",
        "POLYESTER 80% WOOL 20%\nCOTTON 100%",
        "COTTON 100%\nPOLYESTER\n100%",
        "POLYESTER\n100%\nCOTTON 100%",
        "MATERIAL: COTTON 100%\nPOLYESTER 100%",
        "COTTON 100%\nMATERIAL: POLYESTER 100%",
        "COTTON 100\nPOLYESTER 100%",
        "COTTON 100%\nWOOL 100%\nCOTTON 80% POLYESTER 20%",
        "OUTER COTTON 98% SPANDEX 2%\n겉감 면 70% 폴리에스터 25% 폴리우레탄 5%",
        "OUTER COTTON 100%\nOUTER WOOL 80% NYLON 20%\nLINING POLYESTER 100%",
    ],
)
def test_conflict_is_rejected_despite_candidate_rank(text):
    result = parse_label(text)
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert any("ambiguous_composition_candidates" in warning for warning in result["warnings"])
    assert parse_materials(text) == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MATERIAL: COTTON 100%\n면 100%", {"cotton": 100}),
        ("COTTON 100%\nCOTTON\n100%", {"cotton": 100}),
        ("COTTON 100\n면 100%", {"cotton": 100}),
        ("COTTON 98% ELASTANE 2%\n棉 98% 氨纶 2%", {"cotton": 98, "spandex": 2}),
        ("OUTER COTTON 100%\nLINING POLYESTER 80% WOOL 20%", {"cotton": 100}),
        ("OUTER COTTON 100%\nLINING POLYESTER 100%\nLINING WOOL 100%", {"cotton": 100}),
        ("COTTON 100%\nSILK TOUCH 100%", {"cotton": 100}),
    ],
)
def test_equivalent_declarations_and_separate_parts_remain_valid(text, expected):
    result = parse_label(text)
    assert result["status"] == "success"
    assert result["materials"] == expected


def test_near_total_is_incomplete_evidence_not_a_complete_conflicting_candidate():
    result = parse_label("COTTON 50% WOOL 50%\nCOTTON 49.995% WOOL 50%")
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert "generic:unpaired_material_rows" in result["warnings"]


def test_spandex_and_polyurethane_are_distinct_conflicting_declarations():
    result = parse_label("COTTON 98% POLYURETHANE 2%\n棉 98% 氨纶 2%")
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert "generic:ambiguous_composition_candidates" in result["warnings"]


@pytest.mark.parametrize(
    "heading",
    ["", "혼용률", "혼용율", "섬유의 조성", "COMPOSITION", "MATERIALS",
     "FIBER CONTENT", "纤维成分", "品質表示", "混用率"],
)
@pytest.mark.parametrize("before", [False, True])
def test_unpaired_percentages_remain_unsafe_with_composition_heading(heading, before):
    composition = "LYOCELL 50% NYLON 45% POLYURETHANE 5%"
    residual = f"{heading} 57% 38% 5%"
    text = f"{residual}\n{composition}" if before else f"{composition}\n{residual}"

    result = parse_label(text)

    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert "generic:unpaired_ratio_rows" in result["warnings"]
    assert parse_materials(text) == {}


@pytest.mark.parametrize("ratio", ["-5%", "0%", "120%"])
def test_heading_does_not_hide_invalid_ratio(ratio):
    result = parse_label(f"COTTON 100%\nCOMPOSITION {ratio}")
    assert result["status"] == "failed"
    assert "generic:invalid_ratio" in result["warnings"]


@pytest.mark.parametrize(
    "text",
    [
        "OUTER COTTON 100%\nLINING 混用率 57% 38% 5%",
        "COTTON 100%\n호칭 57% 38% 5%",
        "COTTON 100%\nIMMATERIAL 57% 38% 5%",
        "COTTON 100%\nSILK TOUCH 100%",
        "COTTON 100%\nMACHINE WASH 30°C",
    ],
)
def test_heading_ratio_guard_preserves_other_parts_and_non_composition_text(text):
    assert parse_label(text)["materials"] == {"cotton": 100}


def test_outer_heading_residual_cannot_be_replaced_by_complete_lining():
    result = parse_label("OUTER 混用率 57% 38% 5%\nLINING POLYESTER 100%")
    assert result["status"] == "failed"
    assert result["materials"] == {}
    assert "outer:unpaired_ratio_rows" in result["warnings"]
