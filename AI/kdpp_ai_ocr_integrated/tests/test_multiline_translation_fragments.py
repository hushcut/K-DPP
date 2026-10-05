"""Exact multirow aliases and literal translation separators keep all evidence."""

import pytest

from apps.text.ocr_candidates import build_candidate, find_rejected_composition_parts
from apps.text.parse_label import _prepare_multilingual_rows, parse_label


def _prepare_without_losing_characters(text):
    # The helper receives case-folded text; preserve blank rows here so a real
    # double line break cannot be mistaken for one contiguous wrap.
    normalized = text.casefold()
    prepared = _prepare_multilingual_rows(normalized)
    assert "".join(prepared.split()) == "".join(normalized.split())
    return prepared


@pytest.mark.parametrize("fragments, alias, material", [
    ("BA\nUM\nWOLLE", "baumwolle", "cotton"),
    ("ALG\nOD\nÃO", "algodão", "cotton"),
    ("C\nOT\nTON", "cotton", "cotton"),
    ("C\nO\nT\nT\nO\nN", "cotton", "cotton"),
    ("COT\nO\nNE", "cotone", "cotton"),
    ("BAM\nBA\nKI", "bambaki", "cotton"),
    ("B\nA\nU\nM\nW\nO\nL\nLE", "baumwolle", "cotton"),
    ("P\nO\nL\nY\nE\nS\nT\nER", "polyester", "polyester"),
    ("POL\nYES\nTER", "polyester", "polyester"),
    ("É\nLAS\nTHAN\nNE", "élasthanne", "spandex"),
    ("P\nO\nL\nI\nÉ\nS\nT\nER", "poliéster", "polyester"),
    ("S\nPA\nNDEX", "spandex", "spandex"),
    ("AL\nGO\nDÓN", "algodón", "cotton"),
    ("LY\nO\nCELL", "lyocell", "lyocell"),
])
def test_three_to_eight_exact_alias_fragments_restore_a_complete_composition(
    fragments, alias, material,
):
    text = f"100% {fragments}"
    assert _prepare_without_losing_characters(text) == f"100% {alias}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {material: 100}


@pytest.mark.parametrize("text, expected", [
    ("COTTON 100%\n/\nCOTON", {"cotton": 100}),
    ("100% COTTON\n/\nコットン", {"cotton": 100}),
    (
        "COTTON 60%\n/\nALGODÓN\nPOLYESTER 40%\n/\nPOLIÉSTER",
        {"cotton": 60, "polyester": 40},
    ),
    (
        "OUTER\nCOTTON 100%\n/\nCOTON\nLINING NYLON 100%",
        {"cotton": 100},
    ),
    ("NYLON 100%\n/\nナイロン", {"nylon": 100}),
    ("WOOL 100%\n/\nWOLLE", {"wool": 100}),
])
def test_standalone_slash_connects_only_confirmed_same_fiber_translation(text, expected):
    prepared = _prepare_without_losing_characters(text)
    assert "\n/\n" not in prepared
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("text", [
    "100% BA\nUM\nWOLLE / OLEFIN",
    "100% BA\nUM\nWOLLE / UNKNOWN",
    "100% ALG\nOD\nÃO / NYLON",
    "100% C\nOT\nTON / MODACRYLIC",
    "100% POL\nYES\nTER / FAUX LEATHER",
    "100% BA\nUM\nWOLLE / OLEFIN 10%",
    "COTTON 100%\n/\nNYLON",
    "COTTON 100%\n/\nCOTON 20%",
    "COTTON 100%\n/\nCOTON / OLEFIN",
    "COTTON 100%\n/\nUNKNOWN / COTON",
    "COTTON 100%\n/\nSIZE\nCOTON",
    "COTTON 70%\n/\nCOTON",
    "COTTON 100%\n/\nCOTON\n10%",
    "COTTON 100%\n/\nCOTON\nPOLYESTER 10%",
])
def test_linking_does_not_confirm_unknown_extra_or_incomplete_evidence(text):
    _prepare_without_losing_characters(text)
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("text", [
    "100% ba\n\num\nwolle",
    "100% ba\n/\num\nwolle",
    "100% ba\nunknown\num\nwolle",
    "100% ba\n10\num\nwolle",
    "100% ba\num\nwollef",
    "100% polyester\na",
    "100% elastan\ne",
    "100% span\ndex",
    "100% p\no\nl\ny\ne\ns\nt\ne\nr",
    "100% cotton\n/\nsize\ncoton",
    "100% cotton\n/\nnylon",
])
def test_fragments_do_not_cross_gaps_or_change_complete_and_unknown_words(text):
    assert _prepare_without_losing_characters(text) == text


def test_restored_fibers_keep_both_printed_ratios_in_parse_evidence():
    text = "95% BA\nUM\nWOLLE\n5% E\nLAS\nTANE"
    _prepare_without_losing_characters(text)
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 95, "spandex": 5}
    evidence = result["parse_evidence"]
    assert evidence["observed_ratios"] == {"generic": [95.0, 5.0]}
    assert evidence["observed_materials"] == {"generic": ["cotton", "spandex"]}


def test_translation_separator_does_not_link_across_a_new_part_heading():
    text = "COTTON 100%\n/\nLINING\nCOTON"
    prepared = _prepare_without_losing_characters(text)
    assert "\n/\nlining\n" in prepared
    result = parse_label(text)
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "generic"
    assert "lining" not in result["parts"]
    evidence = result["parse_evidence"]
    assert evidence["observed_materials"]["lining"] == ["cotton"]
    assert evidence["rejected_composition_parts"]["lining"] == ["unpaired_material_rows"]


def test_valid_fragment_candidate_does_not_hide_unknown_other_response():
    candidates = [
        build_candidate(
            "original", "100% BA\nUM\nWOLLE\n/\nCOTON", parse_candidate=parse_label,
        ),
        build_candidate(
            "preprocessed", "100% BA\nUM\nWOLLE / OLEFIN 10%", parse_candidate=parse_label,
        ),
    ]
    assert candidates[0].parser_status == "success"
    assert candidates[1].parser_status == "failed"
    assert find_rejected_composition_parts(candidates, selected_part="generic")


@pytest.mark.parametrize("text", [
    "cot\nt\non100% 30",
    "cot\nt\non 100% 30",
    "cot\nt\non 100% 0.5",
    "cot\nt\non 100% 0",
    "cot\nt\non 100% 300",
    "cot\nt\non 100% 0,5",
    "0 cot\nt\non 100%",
    "100% cot\nt\non 30",
    "cot\nt\non 100% -30",
    "+30 cot\nt\non 100%",
    "100% COT\nTON 30",
    "COT\nTON 100% 0.5",
])
def test_restoring_aliases_does_not_hide_unconsumed_printed_numbers(text):
    _prepare_without_losing_characters(text)
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("sign", ["+", "±", "−", "≈", "-", "~", "≤", "≥"])
@pytest.mark.parametrize("position", ["prefix", "suffix", "preceding_row", "following_row"])
def test_restored_alias_cannot_hide_inexact_signs_in_or_beside_the_block(sign, position):
    readings = {
        "prefix": f"{sign} cot\nt\non 100%",
        "suffix": f"100%cot\nt\non {sign}",
        "preceding_row": f"{sign}\ncot\nt\non 100%",
        "following_row": f"cot\nt\non 100%\n{sign}",
    }
    text = readings[position]
    prepared = _prepare_without_losing_characters(text)
    assert "cotton" in prepared
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("position", ["before", "after"])
def test_restored_alias_does_not_hide_an_unknown_neighboring_row(position):
    block = "cot\nt\non 100%"
    text = f"FOO\n{block}" if position == "before" else f"{block}\nFOO"
    prepared = _prepare_without_losing_characters(text)
    assert "cotton" in prepared
    assert "foo" in prepared
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("neighbor, position", [
    ("FOO", "before"), ("FOO", "after"),
    ("≈", "before"), ("≈", "after"),
    ("BAR", "before"), ("BAR", "after"),
    ("+", "before"), ("+", "after"),
])
def test_identical_fiber_rows_in_another_part_cannot_cancel_restored_provenance(neighbor, position):
    # The lining's slash attachment changes a pre-existing cotton row. The
    # outer's restored row has that old spelling, but still comes from three
    # source rows and must retain its own ambiguous neighboring context.
    block = "cot\nt\non 100%"
    outer = f"{neighbor}\n{block}" if position == "before" else f"{block}\n{neighbor}"
    text = f"lining\ncotton 100%\n/\ncoton\nouter\n{outer}"
    prepared = _prepare_without_losing_characters(text)
    assert "cotton 100% /\ncoton" in prepared
    assert "cotton 100%" in prepared.split("outer\n", 1)[1]
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    evidence = result["parse_evidence"]
    assert evidence["observed_materials"]["outer"] == ["cotton"]
    assert "outer" in evidence["rejected_composition_parts"]


@pytest.mark.parametrize("first_part, restored_part", [("lining", "outer"), ("outer", "lining")])
def test_identical_clean_fiber_rows_keep_both_parts_confirmed(first_part, restored_part):
    text = f"{first_part}\ncotton 100%\n/\ncoton\n{restored_part}\ncot\nt\non 100%"
    _prepare_without_losing_characters(text)
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"
    assert result["parts"] == {"outer": {"cotton": 100}, "lining": {"cotton": 100}}
