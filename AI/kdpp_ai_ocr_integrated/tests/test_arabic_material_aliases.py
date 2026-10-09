"""Exact Arabic fiber names preserve all adjacent ratio and token evidence."""

import pytest

from apps.text.material_extraction import _material_evidence, find_material_key
from apps.text.parse_label import parse_label
from apps.text.rules import OCR_CORRECTIONS


@pytest.mark.parametrize("alias, material", [
    ("قطن", "cotton"),
    ("القطن", "cotton"),
    ("بوليستر", "polyester"),
    ("البوليستر", "polyester"),
])
@pytest.mark.parametrize("ratio_first", [False, True])
def test_exact_arabic_fiber_has_its_own_explicit_ratio(alias, material, ratio_first):
    text = f"100% {alias}" if ratio_first else f"{alias} 100%"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {material: 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}
    assert result["parse_evidence"]["paired_material_ratios"] == {
        "generic": [[material, 100.0]],
    }
    assert result["raw_ocr_preview"] == text
    assert alias not in OCR_CORRECTIONS


@pytest.mark.parametrize("text, expected", [
    ("قطن 62%\nبوليستر 38%", {"cotton": 62, "polyester": 38}),
    ("62% القطن\n38% البوليستر", {"cotton": 62, "polyester": 38}),
    ("100% Cotton/ Coton/ القطن/ コットン/ 면", {"cotton": 100}),
    ("100% Cotton/ Coton/\nالقطن/ コットン/ 면", {"cotton": 100}),
    ("Cotton 100%\n/\nقطن", {"cotton": 100}),
    ("بوليستر/\nPolyester 100%", {"polyester": 100}),
    (
        "62% Polyester/\nبوليستر/ ポリエステル\n38% Cotton/\nقطن/ コットン",
        {"cotton": 38, "polyester": 62},
    ),
    ("100% الق\nطن", {"cotton": 100}),
    ("100% بو\nلي\nستر", {"polyester": 100}),
])
def test_registered_arabic_aliases_share_only_the_same_fiber_ratio(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("token", [
    "قطني", "قطنية", "بقطن", "فقطن", "القطني", "قطنون",
    "بوليس", "ابوليستر", "البوليستري", "بوليسترية",
    "all", "aaly", "j", "jail", "E", "rine", "aol",
])
def test_partial_or_unrelated_tokens_do_not_become_arabic_fibers(token):
    assert find_material_key(token) is None
    assert not _material_evidence(token)


@pytest.mark.parametrize("text", [
    "100% Cotton/ بوليستر",
    "Cotton 100%\nقطن 70%\nبوليستر 30%",
    "قطن\nبوليستر",
    "قطن 60%\nبوليستر 30%",
    "100% قطني",
    "100% بقطن",
    "100% Cotton/ all/ コットン",
    "100% Cotton/ jail/ コットン",
    "100% Cotton/ E/ コットン",
    "100% Cot\nton/ القطن/ OLEFIN",
    "100% Cot\nton/ القطن/ مجهول",
    "100% Cot\nton/ القطن 30",
    "100% Cot\nton/ القطن 0.5",
    "100% Cot\nton/ القطن ±",
    "Cotton 100%\n/\nقطن 20%",
    "Cotton 100%\n/\nقطن / OLEFIN",
    "Cotton 100%\n/\nبوليستر",
])
def test_arabic_vocabulary_does_not_hide_unknown_or_conflicting_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_arabic_new_part_is_not_absorbed_as_a_translation():
    result = parse_label("OUTER Cotton 100%\nLINING بوليستر")
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"
    assert "lining" not in result["parts"]
    assert result["parse_evidence"]["observed_materials"]["lining"] == ["polyester"]
    assert result["parse_evidence"]["rejected_composition_parts"]["lining"] == [
        "unpaired_material_rows",
    ]


@pytest.mark.parametrize("alias", ["قطن", "القطن", "بوليستر", "البوليستر"])
@pytest.mark.parametrize("pattern", [
    "not {alias} 100%",
    "بدون {alias} 100%",
    "100% {alias}/OLEFIN",
    "100% {alias}/نايلون",
    "100% {alias} 30",
    "100% {alias} 0.5",
    "{alias} ±100%",
    "{alias} 100% ~",
])
def test_direct_arabic_ratios_cover_every_word_digit_and_sign(alias, pattern):
    text = pattern.format(alias=alias)
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert result["raw_ocr_preview"] == text


@pytest.mark.parametrize("extra", ["0", "30", ".5", "0.5", "0,5", "300", "+30", "-30"])
@pytest.mark.parametrize("before", [False, True])
def test_direct_arabic_row_preserves_unconsumed_numbers(extra, before):
    text = f"{extra} قطن 100%" if before else f"100% قطن {extra}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert result["raw_ocr_preview"] == text


@pytest.mark.parametrize("extra", [
    "0", "0.5", "0,5", "300", "10", "10%", "OLEFIN", "مجهول",
    "نايلون", "not", "بدون", "~", "±", "-", "unknown 0", "0 UNKNOWN",
])
@pytest.mark.parametrize("before", [False, True])
def test_arabic_block_preserves_opaque_numeric_and_sign_neighbor_rows(extra, before):
    text = f"{extra}\nقطن 100%" if before else f"قطن 100%\n{extra}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert result["raw_ocr_preview"] == " ".join(text.split())


@pytest.mark.parametrize("boundary", [
    "SIZE M", "SIZE 0", "신체치수: 100 cm", "SHRINKAGE 5%",
    "MADE IN CHINA", "HAND WASH", "WASH COLD", "DO NOT BLEACH",
])
@pytest.mark.parametrize("before", [False, True])
def test_arabic_ratio_preserves_complete_metadata_origin_and_care_boundaries(boundary, before):
    text = f"{boundary}\nقطن 100%" if before else f"قطن 100%\n{boundary}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}


@pytest.mark.parametrize("text", ["100% قطن", "100% Cotton/ القطن"])
def test_direct_arabic_rows_do_not_claim_multiline_restoration_provenance(text):
    from apps.text.parse_label import build_line_infos

    restored_indices = set()
    infos = build_line_infos(text, restored_indices=restored_indices)
    assert restored_indices == set()
    assert len(infos) == 1
    assert not infos[0].invalid_evidence
    result = parse_label(text)
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}


@pytest.mark.parametrize("extra", ["٠", "١", "٣٠", "٠٫٥"])
@pytest.mark.parametrize("before", [False, True])
def test_arabic_block_does_not_discard_unread_unicode_numeric_rows(extra, before):
    text = f"{extra}\nقطن 100%" if before else f"قطن 100%\n{extra}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert result["raw_ocr_preview"] == " ".join(text.split())
