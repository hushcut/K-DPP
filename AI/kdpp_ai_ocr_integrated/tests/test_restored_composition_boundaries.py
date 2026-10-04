"""Restored multilingual ratios must retain neighboring unknown evidence."""

import pytest

from apps.text.parse_label import build_line_infos, parse_label


TRANSLATED = (
    "COTTON 60% /\nCOTON / ALGODÓN\n"
    "POLYESTER 40% /\nPOLIÉSTER / ポリエステル"
)
RATIO_FIRST = "60%\nCOTTON\n40%\nPOLYESTER"
SINGLE_TRANSLATED = "COTTON 100% /\nCOTON / ALGODÓN"


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("unknown", ["OLEFIN", "UNKNOWN"])
@pytest.mark.parametrize("placement", ["before", "after", "heading_before", "heading_after", "code_before", "code_after"])
def test_restored_composition_does_not_drop_neighboring_opaque_rows(composition, unknown, placement):
    if placement == "before":
        text = f"{unknown}\n{composition}"
    elif placement == "after":
        text = f"{composition}\n{unknown}"
    elif placement == "heading_before":
        text = f"{unknown}\nCOMPOSITION\n{composition}"
    elif placement == "heading_after":
        text = f"{composition}\nFABRIC CONTENT\n{unknown}"
    elif placement == "code_before":
        text = f"{unknown}\n341-404149\n{composition}"
    else:
        text = f"{composition}\n341-404149\n{unknown}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("caption", ["HAND WASH OLEFIN", "DRY CLEAN UNKNOWN", "FOLD DOWN OLEFIN", "DRY FOLD DOWN UNKNOWN"])
def test_care_word_does_not_make_an_opaque_boundary_safe(composition, caption):
    result = parse_label(f"{composition}\n{caption}")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("primary", [
    "COTTON 100% OLEFIN /", "OLEFIN COTTON 100% /",
    "COTTON 100% UNKNOWN /", "UNKNOWN COTTON 100% /",
])
def test_alias_coverage_does_not_hide_opaque_words_on_primary_row(primary):
    result = parse_label(f"{primary}\nCOTON / ALGODÓN")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("caption", [
    "FOLD DOWN", "FOLD DOWN FOR STORAGE", "DRY FOLD DOWN AVOID DIRECT SUNLIGHT",
    "HAND WASH", "MADE IN CHINA", "RN 12345",
])
def test_alias_coverage_keeps_known_inline_caption_and_metadata(caption):
    result = parse_label(f"COTTON 100% {caption}\nCOTON / ALGODÓN")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}


@pytest.mark.parametrize("prefix", ["MADE IN CHINA", "MADE IN KOREA", "RN 12345"])
def test_inline_metadata_before_primary_keeps_material_offsets(prefix):
    result = parse_label(f"{prefix} COTTON 100%\nCOTON / ALGODÓN")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}


@pytest.mark.parametrize("composition,expected", [
    (TRANSLATED, {"cotton": 60, "polyester": 40}),
    (RATIO_FIRST, {"cotton": 60, "polyester": 40}),
    (SINGLE_TRANSLATED, {"cotton": 100}),
])
@pytest.mark.parametrize("caption", ["", "HAND WASH", "HAND WASH 30°C", "FOLD DOWN", "DRY FOR FORD DOWN AVOID DIRECT", "MADE IN KOREA"])
def test_confirmed_translation_and_ratio_first_blocks_remain_supported(composition, expected, caption):
    result = parse_label(f"{composition}\n{caption}")
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("caption", [
    "FOLD DOWN OLEFIN", "FORD DOWN UNKNOWN", "FOLD DOWN POLYESTER",
    "FOLD DOWN DOWN", "OLEFIN FOLD DOWN", "UNKNOWN FORD DOWN",
    "FOLD DOWN 10%", "FOLD DOWN 10", "FOLD DOWN OLEFIN 10%",
    "DRY CLEANING FOR FOLD DOWN OLEFIN AVOID DIRECT",
    "10 FOLD DOWN", "10% FORD DOWN",
])
@pytest.mark.parametrize("inline", [False, True])
def test_storage_masking_retains_unknown_materials_and_numbers(caption, inline):
    text = f"COTTON 100%{' ' if inline else chr(10)}{caption}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    rows = build_line_infos(text)
    assert any("down" in row.materials for row in rows)


@pytest.mark.parametrize("caption", ["FOLD DOWN", "FORD DOWN", "FOLD DOWN FOR STORAGE", "DRY FOLD DOWN AVOID DIRECT SUNLIGHT"])
@pytest.mark.parametrize("inline", [False, True])
def test_complete_literal_storage_captions_remain_supported(caption, inline):
    text = f"COTTON 100%{' ' if inline else chr(10)}{caption}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_materials"] == {"generic": ["cotton"]}


def test_explicit_secondary_part_bounds_restored_primary_block():
    result = parse_label(f"OUTSHELL1\n{TRANSLATED}\nOUTSHELL2\nUNKNOWN")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert result["parts"] == {"outer": {"cotton": 60, "polyester": 40}}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("unknown", ["OLEFIN", "UNKNOWN"])
@pytest.mark.parametrize("inline", [False, True])
def test_repeated_same_part_heading_does_not_hide_earlier_opaque_rows(composition, unknown, inline):
    composition = f"OUTER{' ' if inline else chr(10)}{composition}"
    result = parse_label(f"OUTER\n{unknown}\n{composition}")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("unknown", ["OLEFIN", "UNKNOWN"])
@pytest.mark.parametrize("before", [False, True])
def test_part_heading_cannot_hide_an_opaque_word_on_its_own_row(composition, unknown, before):
    text = f"OUTER {unknown}\nOUTER\n{composition}" if before else f"OUTER\n{composition}\nOUTER {unknown}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("heading", [
    "SIZE", "신체치수", "SHRINKAGE", "SIZE\nSHRINKAGE", "신체치수\nSIZE",
])
@pytest.mark.parametrize("before", [False, True])
def test_empty_metadata_header_is_not_a_confirmed_boundary(composition, heading, before):
    text = f"OLEFIN\n{heading}\n{composition}" if before else f"{composition}\n{heading}\nOLEFIN"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("glyph", ["(300", "130/"])
def test_numeric_care_shape_does_not_hide_opaque_neighbor(composition, glyph):
    result = parse_label(f"{composition}\n{glyph}\nOLEFIN")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("composition", [TRANSLATED, RATIO_FIRST, SINGLE_TRANSLATED])
@pytest.mark.parametrize("field", ["SIZE\nM", "SIZE: L", "신체치수\n108"])
def test_complete_explicit_metadata_field_can_bound_a_restored_block(composition, field):
    result = parse_label(f"{composition}\n{field}")
    assert result["status"] == "success", result
    expected = {"cotton": 100} if composition == SINGLE_TRANSLATED else {"cotton": 60, "polyester": 40}
    assert result["materials"] == expected
