"""A bounded product/inspection block cannot supply or erase fiber ratios."""

import importlib

import pytest

from apps.text.ocr_candidates import build_candidate, find_rejected_composition_parts
from apps.text.parse_label import build_line_infos, parse_label


def inspected_block(*, stamp_layout="separate", digits="14 100 03", code="ABCD6X123", date="제조년월: 2021.07"):
    if stamp_layout == "wrapped":
        first, second, third = digits.split()
        return f"{code}\n{first} {second}\n{third} 검사필\n{date}"
    code_row = f"{code} 검사필" if stamp_layout == "inline" else code
    tail = date if stamp_layout == "inline" else f"검사필\n{date}"
    return f"{code_row}\n{digits}\n{tail}"


@pytest.mark.parametrize("composition", [
    "겉감\nWOOL 100%", "겉감\n100%\nWOOL", "겉감\nWOOL\n100%",
])
@pytest.mark.parametrize("stamp_layout", ["separate", "inline", "wrapped"])
@pytest.mark.parametrize("date", ["제조년월: 2021.07", "제조 년 월 : 2022-12"])
def test_confirmed_composition_is_not_rejected_by_an_inspected_product_block(composition, stamp_layout, date):
    text = composition + "\n" + inspected_block(stamp_layout=stamp_layout, date=date)
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"wool": 100}
    assert result["selected_part"] == "outer"
    assert result["parse_evidence"]["observed_ratios"] == {"outer": [100.0]}
    numeric_row = "14 100" if stamp_layout == "wrapped" else "14 100 03"
    info = next(row for row in build_line_infos(text) if row.normalized == numeric_row)
    assert info.is_metadata
    assert not info.numbers and not info.invalid_evidence


@pytest.mark.parametrize("digits", [
    "14 110 03%", "14 110 03 POLYESTER", "14 110 03 UNKNOWN",
    "14 110 03 MODACRYLIC", "-14 110 03", "+14 110 03",
    "14.5 110 03", "14,5 110 03", "14 110 03 05",
    "20 30 50", "020 030 050", "14 10 03",
])
def test_numeric_or_material_evidence_is_not_rewritten_as_a_product_identifier(digits, monkeypatch):
    text = "겉감\nWOOL 100%\n" + inspected_block(digits=digits)
    result = parse_label(text)
    infos = build_line_infos(text)
    parser_module = importlib.import_module("apps.text.parse_label")
    # Older rules already recognize some mixed identifier rows. The new
    # product-block rule must not change any of their evidence or decisions.
    with monkeypatch.context() as patch:
        patch.setattr(parser_module, "_mark_inspected_product_identifiers", lambda rows: rows)
        assert build_line_infos(text) == infos
        assert parse_label(text) == result


@pytest.mark.parametrize("block", [
    "14 110 03\n검사필\n제조년월: 2021.07",
    "ABCD6X123\n14 110 03\n제조년월: 2021.07",
    "ABCD6X123\n14 110 03\n검사\n제조년월: 2021.07",
    "ABCD6X123\n14 110 03\n검사필 UNKNOWN\n제조년월: 2021.07",
    "ABCD6X123\n14 110 03\n검사필\n2021.07",
    "ABCD6X123\n14 110 03\n검사필\n제조년월: 2021.13",
    "ABCD6X123\n14 110 03\n검사필\n제조년월: 2021.07 5%",
    "ABCD6X123\n14 110 03\n검사필\nLINING\n제조년월: 2021.07",
])
def test_each_metadata_boundary_must_be_readable_and_adjacent(block):
    result = parse_label("겉감\nWOOL 100%\n" + block)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("prefix", [
    "겉감\nWOOL 90%", "겉감\nWOOL", "겉감\nUNKNOWN 100%",
    "겉감\nWOOL 100%\nUNKNOWN",
])
def test_metadata_cannot_complete_or_borrow_an_uncertain_composition(prefix):
    result = parse_label(prefix + "\n" + inspected_block())
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_another_part_cannot_supply_the_complete_preceding_composition():
    text = "겉감\nWOOL 100%\nLINING\n" + inspected_block()
    assert not any(row.is_metadata and row.normalized == "14 100 03"
                   for row in build_line_infos(text))
    result = parse_label(text)
    assert result["parts"] == {"outer": {"wool": 100}}


def test_same_response_metadata_keeps_raw_and_layout_candidates_consistent():
    candidates = [
        build_candidate("original", "겉감\nWOOL 100%\n" + inspected_block(), parse_candidate=parse_label),
        build_candidate("original", "겉감\n100%\nWOOL\n" + inspected_block(stamp_layout="wrapped"),
                        parse_candidate=parse_label, layout_used=True),
    ]
    assert all(candidate.parser_status == "success" for candidate in candidates)
    assert find_rejected_composition_parts(candidates, selected_part="outer") == {}
