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
        "COTTON 50% WOOL 50%\nCOTTON 49.995% WOOL 50%",
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
        ("COTTON 98% POLYURETHANE 2%\n棉 98% 氨纶 2%", {"cotton": 98, "polyurethane": 2}),
        ("OUTER COTTON 100%\nLINING POLYESTER 80% WOOL 20%", {"cotton": 100}),
        ("OUTER COTTON 100%\nLINING POLYESTER 100%\nLINING WOOL 100%", {"cotton": 100}),
        ("COTTON 100%\nSILK TOUCH 100%", {"cotton": 100}),
    ],
)
def test_equivalent_declarations_and_separate_parts_remain_valid(text, expected):
    result = parse_label(text)
    assert result["status"] == "success"
    assert result["materials"] == expected
