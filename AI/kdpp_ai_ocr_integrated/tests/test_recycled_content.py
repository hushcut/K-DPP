"""Recycled-property percentages never replace printed fiber percentages."""

import pytest

from apps.text.candidate_evidence import _has_explicit_complete_pairs, row_has_explicit_pairs
from apps.text.material_extraction import (
    _strip_excluded_segments, declared_part, extract_materials, normalize_text,
)
from apps.text.ocr_candidates import build_candidate
from apps.text.parse_label import build_line_infos, extract_numbers, parse_label


@pytest.mark.parametrize("fiber", ["POLYESTER 100%", "100% POLYESTER"])
@pytest.mark.parametrize("property", [
    "(100% RECYCLED)", "(50% RECYCLED)", "(62.5% RECYCLED)", "(62,5% RECYCLÉ)",
    "(100% RECYCLE)", "(100% RECYCLÉ)", "(再生)",
])
def test_closed_property_retains_the_primary_ratio_and_original_caption(fiber, property):
    text = f"{fiber} {property}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}
    assert property in result["raw_ocr_preview"]
    normalized = normalize_text(text)
    assert normalized.count("%") == text.count("%")
    assert _strip_excluded_segments(normalized).count("%") == 1
    row = next(info for info in build_line_infos(text) if info.materials)
    assert row_has_explicit_pairs(row)
    candidate = build_candidate("original", text, parse_candidate=parse_label)
    assert _has_explicit_complete_pairs(candidate)


@pytest.mark.parametrize("property", [
    "(100%\nRECYCLED)", "(100\n% RECYCLED)", "(100% RECYCLED\n)",
    "(\n100% RECYCLE\n)", "(\n再生\n)",
])
def test_only_the_closed_propertys_internal_newlines_are_joined(property):
    text = f"MAIN MATERIAL:\n100% POLYESTER {property}\nLINING:\nNYLON 100%"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["parts"] == {"outer": {"polyester": 100}, "lining": {"nylon": 100}}
    normalized = normalize_text(text)
    assert normalized.count("\n") == 3
    assert normalized.count("%") == text.count("%")
    assert all(row_has_explicit_pairs(info) for info in build_line_infos(text) if info.materials)
    assert "RECYCLED" in result["raw_ocr_preview"] or "RECYCLE" in result["raw_ocr_preview"] or "再生" in result["raw_ocr_preview"]


@pytest.mark.parametrize("text", [
    "POLYESTER 95% (100% RECYCLED)/ELASTANE 5%",
    "95% POLYESTER (100% RECYCLED)/5% ELASTANE",
    "POLYESTER 95% (50% RECYCLE), ELASTANE 5%",
    "95% POLYESTER (100%\nRECYCLED)\n5% ELASTANE",
])
def test_property_does_not_change_the_named_components_mixture(text):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 95, "spandex": 5}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [95.0, 5.0]}
    assert all(row_has_explicit_pairs(info) for info in build_line_infos(text) if info.materials)


@pytest.mark.parametrize("text,expected", [
    ("100% 聚酯纤维(再生)", {"polyester": 100}),
    ("聚酯纖維 100% (再生)", {"polyester": 100}),
    ("100% 再生纤维素纤维", {"viscose": 100}),
    ("再生纖維素纖維 100%", {"viscose": 100}),
    ("COTTON 60% (RECYCLED POLYESTER 40%)", {"cotton": 60, "polyester": 40}),
])
def test_han_fiber_names_and_actual_parenthesized_fibers_are_preserved(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected
    if "纤维素" in text or "纖維素" in text:
        assert "再生" in _strip_excluded_segments(normalize_text(text))
    if "POLYESTER 40%" in text or "40% RECYCLED POLYESTER" in text:
        assert _strip_excluded_segments(normalize_text(text)).count("%") == 2


@pytest.mark.parametrize("text", [
    "COTTON 60% (RECYCLED POLYESTER 40%)",
    "COTTON 60% (40% RECYCLED POLYESTER)",
])
def test_actual_parenthesized_fiber_is_not_masked_as_a_property(text):
    # Mixed ratio-first rows have independent parser constraints. Both fiber
    # names and both literal values must survive the recycled-property view.
    view = _strip_excluded_segments(normalize_text(text))
    assert extract_materials(view) == ["cotton", "polyester"]
    assert extract_numbers(view) == [60, 40]


@pytest.mark.parametrize("property", [
    "(100% UNKNOWN)", "(100% UNREGISTERED)", "(100% NOT RECYCLED)",
    "(100% RECYCLED UNKNOWN)", "(100% RECYCLED NYLON)",
    "(100% RECYCLED 5% NYLON)", "(100% RECYCLED 5%)", "(100% RECYCLED 5)",
    "(100% RECYCLED ±)", "(100% RECYCLED ?)", "(~100% RECYCLED)",
    "(±100% RECYCLED)", "(-100% RECYCLED)", "(+100% RECYCLED)",
    "(0% RECYCLED)", "(101% RECYCLED)", "(100.01% RECYCLED)",
    "(100% RECYCLED", "100% RECYCLED)", "[100% RECYCLED]", "(100% RECYCLED]",
    "((100% RECYCLED))", "(100% RECYCLED (NYLON))", "(100%\nUNKNOWN\nRECYCLED)",
    "(100%\nMAIN MATERIAL\nRECYCLED)", "(再生纤维素纤维)", "(再生 5%)",
])
def test_opaque_extra_uncertain_or_incomplete_properties_remain_evidence(property):
    text = f"POLYESTER 100% {property}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    # Invalid captions are not silently converted into the complete base row.
    assert _strip_excluded_segments(normalize_text(text)) != "polyester 100%"


@pytest.mark.parametrize("prefix", ["NOT", "NO", "UNKNOWN", "MYSTERY", "UNREGISTERED"])
@pytest.mark.parametrize("fiber", ["POLYESTER 100%", "100% POLYESTER"])
def test_a_property_cannot_remove_an_opaque_or_negating_component_prefix(prefix, fiber):
    text = f"{prefix} {fiber} (100% RECYCLED)"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert "(100% recycled)" in _strip_excluded_segments(normalize_text(text))


@pytest.mark.parametrize("suffix", ["NOT", "UNKNOWN", "MYSTERY", "UNREGISTERED", "(NOT RECYCLED)"])
@pytest.mark.parametrize("fiber", ["POLYESTER 100%", "100% POLYESTER"])
def test_a_property_cannot_leave_an_opaque_or_negating_component_suffix(suffix, fiber):
    text = f"{fiber} (100% RECYCLED) {suffix}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert "(100% recycled)" in _strip_excluded_segments(normalize_text(text))


@pytest.mark.parametrize("separator", ["/", ";"])
def test_a_preceding_complete_pair_needs_an_explicit_separator(separator):
    text = f"COTTON 60%{separator}POLYESTER 40% (100% RECYCLED)"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert row_has_explicit_pairs(next(info for info in build_line_infos(text) if info.materials))
    bad = f"MYSTERY {text}"
    assert parse_label(bad)["status"] == "failed"
    assert "(100% recycled)" in _strip_excluded_segments(normalize_text(bad))


@pytest.mark.parametrize("text", [
    "POLYESTER 70% (100% RECYCLED)",
    "POLYESTER 95% (5% RECYCLED)",
    "POLYESTER (100% RECYCLED)",
    "POLYESTER (100%\nRECYCLED)",
    "POLYESTER (100% RECYCLED",
    "POLYESTER (100%\nRECYCLED",
    "POLYESTER (100% RECYCLE)",
    "POLYESTER (100% RECYCLÉ)",
    "(100% RECYCLED) POLYESTER",
    "(100% RECYCLED)",
    "(100% RECYCLED) POLYESTER 100%",
    "POLYESTER 100%\nUNKNOWN\n(100% RECYCLED)",
])
def test_property_cannot_supply_a_missing_fiber_ratio_or_borrow_a_previous_row(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_a_part_boundary_keeps_the_standalone_property_unpaired():
    text = "OUTER POLYESTER 100%\nLINING\n(100% RECYCLED)"
    row = build_line_infos(text)[-1]
    assert row.part == "lining"
    assert row.numbers == (100,)
    assert not row.is_metadata
    assert "(100% recycled)" in _strip_excluded_segments(normalize_text(text))


@pytest.mark.parametrize("fiber", ["POLYESTER 100%", "100% POLYESTER"])
@pytest.mark.parametrize("property", ["(100% RECYCLED)", "(50% RECYCLE)", "(100% RECYCLÉ)", "(再生)"])
def test_a_closed_next_row_property_binds_only_to_its_preceding_literal_pair(fiber, property):
    text = f"MAIN MATERIAL:\n{fiber}\n{property}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"polyester": 100}
    assert result["parse_evidence"]["observed_ratios"] == {"outer": [100.0]}
    assert property in result["raw_ocr_preview"]
    rows = [info for info in build_line_infos(text) if info.materials]
    assert len(rows) == 1 and row_has_explicit_pairs(rows[0])
    assert _has_explicit_complete_pairs(build_candidate("original", text, parse_candidate=parse_label))


def test_a_next_row_property_retains_a_partial_components_actual_ratio():
    text = "RIB PART:\n95% POLYESTER\n(100% RECYCLED)/\n5% ELASTANE"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "rib"
    assert result["materials"] == {"polyester": 95, "spandex": 5}
    assert result["parse_evidence"]["observed_ratios"] == {"rib": [95.0, 5.0]}
    assert all(row_has_explicit_pairs(info) for info in build_line_infos(text) if info.materials)


@pytest.mark.parametrize("text", [
    "POLYESTER\n100%\n(100% RECYCLED)",
    "POLYESTER 100\n(100% RECYCLED)",
    "100% UNKNOWN\n(100% RECYCLED)",
    "POLYESTER\n(100% RECYCLED)",
    "POLYESTER 70%\n(30% RECYCLED)",
    "POLYESTER 100%\nUNKNOWN\n(100% RECYCLED)",
    "POLYESTER 100%\nNOT\n(100% RECYCLED)",
    "POLYESTER 100%\n(100% RECYCLED) UNKNOWN",
    "POLYESTER 100%\n(100% RECYCLED) NOT",
    "POLYESTER 100%\n(100% RECYCLED)\nUNKNOWN",
    "POLYESTER 100%\n(100% RECYCLED)\nNOT",
    "POLYESTER 100%\n(100% RECYCLED",
])
def test_a_next_row_property_never_completes_missing_or_uncertain_material_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("boundary", ["LINING:", "RIB PART:", "MAIN MATERIAL:"])
def test_a_next_row_property_cannot_cross_even_a_same_part_heading(boundary):
    text = f"MAIN MATERIAL:\nPOLYESTER 100%\n{boundary}\n(100% RECYCLED)"
    rows = build_line_infos(text)
    property_row = next(info for info in rows if info.normalized == "(100% recycled)")
    assert property_row.numbers == (100,)
    assert not property_row.is_metadata
    assert not row_has_explicit_pairs(property_row)
    # A valid outer may still be selected while a lower-priority part fails;
    # that policy must not turn this unbound property into a lining/rib fiber.
    assert all(info.materials == () for info in rows if info.index >= property_row.index)


@pytest.mark.parametrize("heading", [
    "MAIN MATERIAL", "GB: MAIN MATERIAL", "MATIERE PRINCIPALE", "F: MATIERE PRINCIPALE",
    "MATIÈRE PRINCIPALE", "FR: MATIÈRE PRINCIPALE", "主料", "CN:主料",
])
def test_literal_main_headings_select_outer_ahead_of_rib_or_lining(heading):
    text = f"{heading}:\n100% POLYESTER (100% RECYCLED)\nRIB: POLYESTER 95% ELASTANE 5%\nLINING: NYLON 100%"
    result = parse_label(text)
    assert declared_part(heading + ":") == "outer"
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"polyester": 100}
    assert result["parts"]["rib"] == {"polyester": 95, "spandex": 5}
    assert "representative_part_fallback:lining" not in result["warnings"]


@pytest.mark.parametrize("heading", [
    "NOT MAIN MATERIAL", "NO MAIN MATERIAL", "THE MAIN MATERIAL", "MAIN MATERIALS",
    "MAIN MATERIAL UNKNOWN", "NOT MATIERE PRINCIPALE", "F: NOT MATIÈRE PRINCIPALE",
    "非主料", "非主料:100%聚酯纤维", "CN:非主料", "主料不明", "WORD MAIN MATERIAL",
    "NOT EMPIECEMENT EN BORD COTE", "THE EMPIÈCEMENT EN BORD CÔTE",
])
def test_new_part_aliases_do_not_retag_negated_embedded_or_opaque_headings(heading):
    assert declared_part(heading + ":") is None


@pytest.mark.parametrize("heading", [
    "RIB PART", "EMPIECEMENT EN BORD COTE", "EMPIÈCEMENT EN BORD CÔTE",
    "F: EMPIECEMENT EN BORD COTE",
])
def test_complete_rib_headings_own_their_material_ratio_rows(heading):
    text = f"{heading}: 95% POLYESTER (100% RECYCLE)/5% ELASTANE"
    result = parse_label(text)
    assert declared_part(heading + ":") == "rib"
    assert result["status"] == "success", result
    assert result["selected_part"] == "rib"
    assert result["materials"] == {"polyester": 95, "spandex": 5}


@pytest.mark.parametrize("heading", [
    "EMPIECEMENT\nEN BORD COTE", "EMPIÈCEMENT\nEN BORD CÔTE",
    "F: EMPIECEMENT\nEN BORD COTE", "RIB\nPART",
])
def test_exact_wrapped_rib_heading_preserves_the_main_and_rib_ownership(heading):
    text = ("MAIN MATERIAL:\n100% POLYESTER\n(100% RECYCLED)\n"
            f"{heading}: 95% POLYESTER\n(100% RECYCLÉ)/5% ELASTANE")
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"polyester": 100}, "rib": {"polyester": 95, "spandex": 5},
    }
    assert declared_part(normalize_text(heading + ":")) == "rib"
    assert "rib:composition_not_confirmed" not in result["warnings"]


@pytest.mark.parametrize("heading", ["EMPIECEMENT\nEN BORD COTE", "RIB\nPART"])
def test_a_property_slash_and_wrapped_next_heading_remain_separate_parts(heading):
    text = ("F: MATIERE PRINCIPALE:\n100% POLYESTER\n"
            f"(100% RECYCLE)/{heading}: 95% POLYESTER\n"
            "(100% RECYCLE)/5% ELASTANE")
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"polyester": 100}
    assert result["parts"]["rib"] == {"polyester": 95, "spandex": 5}
    assert result["raw_ocr_preview"].count("%") == text.count("%")


@pytest.mark.parametrize("heading", [
    "NOT EMPIECEMENT\nEN BORD COTE", "EMPIECEMENT\nUNKNOWN\nEN BORD COTE",
    "EMPIECEMENT\nNOT EN BORD COTE", "EMPIECEMENT\nOUTER\nEN BORD COTE",
    "EMPIECEMENT\nEN BORD COTON",
])
def test_wrapped_heading_restoration_does_not_skip_unknown_negating_or_part_rows(heading):
    assert declared_part(normalize_text(heading + ":")) != "rib"
    text = ("MAIN MATERIAL: 100% POLYESTER (100% RECYCLED)\n"
            f"{heading}: 95% POLYESTER (100% RECYCLED)/5% ELASTANE")
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_an_unconfirmed_main_material_prevents_a_lining_fallback():
    result = parse_label("MAIN MATERIAL:\nPOLYESTER 70% (100% RECYCLED)\nLINING: NYLON 100%")
    assert result["status"] == "failed", result
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == {}


@pytest.mark.parametrize("caption", [
    "UNKNOWN", "NOT", "UNREGISTERED", "알 수 없는 소재", "未知繊維", "未知纤维", "不明",
])
@pytest.mark.parametrize("position", ["before", "after", "heading"])
def test_main_property_does_not_erase_separate_explicit_unknown_or_negating_text(caption, position):
    fiber = "POLYESTER 100% (100% RECYCLED)"
    if position == "heading":
        text = f"MAIN MATERIAL: {caption}\n{fiber}"
    elif position == "before":
        text = f"MAIN MATERIAL:\n{caption}\n{fiber}"
    else:
        text = f"MAIN MATERIAL:\n{fiber}\n{caption}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert caption in result["raw_ocr_preview"]


@pytest.mark.parametrize("first,second", [(100, 50), (50, 100), (25, 75)])
def test_conflicting_properties_of_the_same_printed_component_are_not_both_removed(first, second):
    text = f"POLYESTER 100% ({first}% RECYCLED)({second}% RECYCLE)"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert _strip_excluded_segments(normalize_text(text)).count("%") > 1


def test_different_components_may_have_different_recycled_content():
    text = "COTTON 60% (50% RECYCLED)/POLYESTER 40% (100% RECYCLED)"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert row_has_explicit_pairs(next(info for info in build_line_infos(text) if info.materials))


@pytest.mark.parametrize("separator", ["/", ",", ";"])
def test_a_decimal_comma_in_the_next_fiber_ratio_is_not_a_separator(separator):
    text = f"POLYESTER 97,5% (100% RECYCLED){separator}ELASTANE 2,5%"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 97.5, "spandex": 2.5}
    assert row_has_explicit_pairs(next(info for info in build_line_infos(text) if info.materials))


def test_recycled_pair_verification_does_not_newly_hide_trim_percentages():
    text = "COTTON 100% (TRIM NYLON 5%)"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    # Composition exclusion is established behavior. Reread confirmation has
    # a separate obligation to account for every explicit percentage.
    row = next(info for info in build_line_infos(text) if info.materials)
    assert not row_has_explicit_pairs(row)
    assert not _has_explicit_complete_pairs(build_candidate("original", text, parse_candidate=parse_label))
