"""Repeated registered copies may explain damage; never invent a primary."""

import pytest
from dataclasses import replace

from apps.text.parse_label import parse_label
from apps.text.ocr_candidates import (
    agreed_original_composition, build_candidate, find_rejected_composition_parts,
)
from apps.text.ocr_layout import OcrWord


@pytest.mark.parametrize("text, expected", [
    ("100% Cotton/Coton/Baumwolle/ji/コットン", {"cotton": 100}),
    ("100% Cotton/Coton/Ba\numwolle/Algodao/all/コットン/", {"cotton": 100}),
    (
        "62% Polyester/Poliéste\nポリエステル\n"
        "33% Cotton/Coton/Baumwolle/Algodão/ji/コットン\n"
        "5% Elastane/Élasthann\ne/Elasthan/Elastano/!\nY/エラスタン\n"
        "30\nWASH WITH LIKE COLORS",
        {"polyester": 62, "cotton": 33, "spandex": 5},
    ),
    ("OUTER\n100% Cotton/Coton/Baumwolle/ji/コットン\nLINING NYLON 100%", {"cotton": 100}),
])
def test_primary_and_agreeing_registered_copies_explain_bounded_damage(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected
    assert "damaged_translation_fragment" in result["warnings"]
    assert result["confidence"]["parser"] == "medium"
    assert result["raw_ocr_preview"]  # Raw preview is never replaced by the simplified list.


@pytest.mark.parametrize("tail", [
    "OLEFIN", "UNKNOWN", "MODACRYLIC", "木纤维", "FAUX LEATHER", "OTHER",
    "NYLON", "POLYESTER 20%", "5%", "0", "0.5", "-5", "+5", "≈", "≤",
    "CUSTOMFIBER", "ABCDEF", "abc", "LINING", "faux", "synthetic",
])
def test_unresolved_or_extra_evidence_is_not_a_translation(tail):
    result = parse_label(f"100% Cotton/Coton/Baumwolle/{tail}")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("text", [
    "100% Cotton/ji/コットン",  # Fewer than three distinct copies for short noise.
    "100% Cotton/Coton/ABCDEF/コットン",
    "100% Cotton/Coton/Baumwolle/Alg\nodaof unknown",  # No dropped continuation.
    "100% Cotton/Coton/Baumwolle/\nUNKNOWN",
    "100% Cotton/Coton/Baumwolle/\nOPAQUE SUFFIX",
    "70% Cotton/Coton/Baumwolle/ji/コットン",  # No ratio balancing.
    "100 Cotton/Coton/Baumwolle/ji/コットン",  # No guessed percentage marker.
    "100% Cot/Coton/Baumwolle/ji/コットン",  # Primary must be complete.
    "100% Cotton/Coton/Baumwolle/ji/コットン\n10%",
    "OUTER\n95% Cotton/Coton/Baumwolle/ji/コットン\nLINING NYLON 100%",
    "OUTER\nFAUX FUR\nLINING\n100% Cotton/Coton/Baumwolle/ji/コットン",
    "OUTER 1\n100% Cotton/Coton/Baumwolle/ji/コットン\nOUTER 2 NYLON 100%",
    "100% Cotton/Coton/Baumwolle/ji/コットン\n100% NYLON",
])
def test_primary_part_conflicts_and_incomplete_compositions_still_fail(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("word", ["PU", "PA", "PE", "PP", "PES", "PLA", "MIX", "UNK", "NY", "WO", "ELA"])
def test_short_ambiguous_material_names_are_not_ignored_as_damage(word):
    result = parse_label(f"100% Cotton/Coton/{word}/Baumwolle/コットン")
    assert result["status"] == "failed", result


@pytest.mark.parametrize("word", ["UNKNOWN", "OLEFIN", "MODACRYLIC", "木纤维"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_adjacent_unresolved_material_still_blocks_the_list(word, side):
    primary = "100% Cotton/Coton/Baumwolle/ji/コットン"
    text = f"{word}\n{primary}" if side == "before" else f"{primary}\n{word}"
    assert parse_label(text)["status"] == "failed"


def _paired_views():
    text = "100% Cotton/Coton/Baumwolle/ji/コットン"
    words = tuple(OcrWord(token, 0, i * 10, 100, i * 10 + 8) for i, token in enumerate(text.split()))
    metadata = dict(image_key="same-image", image_variant_key="same-response", image_words=words,
                    image_region=(0, 0, 100, 100))
    raw = replace(build_candidate("original", text, parse_candidate=parse_label), **metadata)
    layout = replace(build_candidate("original", text.replace("/", " / "),
                                    parse_candidate=parse_label, layout_used=True), **metadata)
    return raw, layout


def test_identical_response_with_complete_primary_pairs_does_not_need_extra_ocr():
    raw, layout = _paired_views()
    assert agreed_original_composition([raw, layout])
    assert raw.parser_confidence == layout.parser_confidence == "medium"


@pytest.mark.parametrize("change", [
    {"image_variant_key": "other-response"},
    {"image_region": (0, 0, 90, 90)},
    {"image_words": ()},
    {"parser_warnings": ("damaged_translation_fragment", "unlabeled_garment_size_inferred")},
    {"paired_material_ratios": {}},
    {"text": "100% Cotton/Coton/Baumwolle/unknown/コットン"},
    {"parts": {"generic": {"nylon": 100}}},
])
def test_agreement_cannot_cross_response_or_skip_missing_and_changed_evidence(change):
    raw, layout = _paired_views()
    assert not agreed_original_composition([raw, replace(layout, **change)])


def test_successful_translation_list_cannot_erase_unknown_fiber_in_another_response():
    raw, _ = _paired_views()
    rejected = build_candidate("preprocessed", "100% Cotton/Coton/Baumwolle/OLEFIN", parse_candidate=parse_label)
    assert find_rejected_composition_parts([raw, rejected], selected_part="generic")


def test_unproven_original_row_correspondence_cannot_be_excused_as_translation_damage(monkeypatch):
    import importlib

    parser = importlib.import_module("apps.text.parse_label")
    monkeypatch.setattr(parser, "_multilingual_restored_row_indices", lambda *_args: None)
    result = parser.parse_label("100% Cotton/Coton/Baumwolle/ji/コットン")
    assert result["status"] == "failed"
    assert result["materials"] == {}
