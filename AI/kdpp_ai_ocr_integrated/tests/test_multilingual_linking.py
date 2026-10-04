"""다국어 반복·줄 연결과 미확정 조성 보존 검사."""

import pytest

from apps.text.ocr_candidates import build_candidate, find_rejected_composition_parts
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("text, expected", [
    (
        "62% POLYESTER / POLIÉSTER\nポリエステル /\n"
        "33% COTTON / COTON / BAU\nMWOLLE / ALGODÓN / ALGOD\nÃO / コットン\n"
        "5% ELASTANE / ÉLASTHANN\nE / ELASTHAN / ELASTANO / エラスタン",
        {"polyester": 62, "cotton": 33, "spandex": 5},
    ),
    (
        "COTTON / COTON\nALGODÓN / ALGODÃO\n60%\n"
        "POLYESTER / POLIÉSTER\nポリエステル\n40%",
        {"cotton": 60, "polyester": 40},
    ),
    (
        "60%\nCOTTON / COTON\nALGODÓN / ALGODÃO\n"
        "40%\nPOLYESTER / POLIÉSTER\nポリエステル",
        {"cotton": 60, "polyester": 40},
    ),
    (
        "60% COTTON / COTON\nALGODÓN / ALGODÃO\n"
        "POLYESTER / POLIÉSTER\nポリエステル\n40%",
        {"cotton": 60, "polyester": 40},
    ),
    ("COTTON 100% /\nコットン", {"cotton": 100}),
    ("100%\nCOTTON / COTON\nコットン", {"cotton": 100}),
    ("COTTON / COTON\nコットン\n100%", {"cotton": 100}),
    ("COTTON 95\n%\nSPANDEX 5\n%", {"cotton": 95, "spandex": 5}),
    ("95\n%\nCOTTON\n5\n%\nSPANDEX", {"cotton": 95, "spandex": 5}),
    (
        "EN: 60% COTTON 40% POLYESTER\nFR: 60% COTON 40% POLIÉSTER",
        {"cotton": 60, "polyester": 40},
    ),
    ("UK: 100% COTTON FR: 100% COTON JP: 100% コットン", {"cotton": 100}),
    ("UK : 100 %\nCOTTON\nFR : 100 %\nCOTON", {"cotton": 100}),
    (
        "OUTER 60% COTTON / COTON\nALGODÓN / ALGODÃO\n40% POLYESTER / POLIÉSTER\n"
        "ポリエステル\nLINING 100% NYLON",
        {"cotton": 60, "polyester": 40},
    ),
])
def test_complete_multilingual_compositions_are_linked(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("split, expected", [
    ("COT\nTON", "cotton"),
    ("BAU\nMWOLLE", "cotton"),
    ("ALGOD\nÃO", "cotton"),
    ("POLYES\nTER", "polyester"),
    ("ÉLASTHANN\nE", "spandex"),
])
def test_exact_registered_alias_split_at_line_wrap_is_restored(split, expected):
    result = parse_label(f"100% {split}")
    assert result["status"] == "success", result
    assert result["materials"] == {expected: 100}


@pytest.mark.parametrize("text", [
    "COTTON 100%\nCOTON",
    "COTTON 100% /\nCOTON / NYLON",
    "COTTON 100% /\nMODACRYLIC / COTON",
    "COTTON 100% /\nOLEFIN / COTON",
    "COTTON 100% /\nUNKNOWN / COTON",
    "COTTON 100% /\nCOTON / OLEFIN 10%",
    "COTTON 100% /\nCOTON 20%",
    "COTTON 100% /\nCOTON\n10%",
    "COTTON 70% /\nCOTON / ALGODÓN",
    "COTTON 60% /\nCOTON\nPOLYESTER 20% /\nPOLIÉSTER",
    "COTTON 60% /\nCOTON\nPOLYESTER 50% /\nPOLIÉSTER",
    "COTTON 95% /\nCOTON\nSPANDEX -5% /\nELASTANE",
    "COTTON 100% /\nCOTON\nPOLYESTER 130%",
    "COTTON / COTON\nSIZE\n100%",
    "COTTON / COTON\nLINING\n100%",
    "OUTER COTTON 60% /\nCOTON\nLINING POLYESTER 40% /\nPOLIÉSTER",
    "COTTON / COTON\nALGODÓN / ALGODÃO\n60%\n40%",
    "60%\nCOTTON / COTON\n100%\nSPANDEX / ELASTANE\n40%",
    "COTTON 100%\nEN: 20% OLEFIN",
    "EN: 60% COTTON 40% POLYESTER\nFR: 70% COTON 30% POLIÉSTER",
    "EN: 100% COTTON\nFR: 100% NYLON",
    "100% MOD\nACRYLIC",
    "COTTON 9596\n%\nSPANDEX 596\n%",
    "COTTON 100%\n5\n%",
    "COTTON 100% /\nFAUX\nLEATHER / LEATHER",
    "COTTON 100% /\nCOTON\nPOLYURETHANE 5% /\nELASTANE 5%",
])
def test_multilingual_linking_does_not_hide_invalid_or_unconfirmed_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_translation_row_evidence_is_kept_after_linking():
    result = parse_label("60% COTTON / COTON\nALGODÓN / ALGODÃO\n40% POLYESTER / POLIÉSTER\nポリエステル")
    assert result["status"] == "success", result
    evidence = result["parse_evidence"]
    assert evidence["observed_ratios"] == {"generic": [60.0, 40.0]}
    assert evidence["observed_materials"] == {"generic": ["cotton", "cotton", "polyester", "polyester"]}


def test_correct_multilingual_candidate_does_not_hide_unknown_fiber_in_other_candidate():
    candidates = [
        build_candidate("original", "COTTON 100% /\nCOTON / コットン", parse_candidate=parse_label),
        build_candidate("preprocessed", "COTTON 100%\nOLEFIN 10%", parse_candidate=parse_label),
    ]
    assert candidates[0].parser_status == "success"
    assert find_rejected_composition_parts(candidates, selected_part="generic")


@pytest.mark.parametrize("name", ["ÉLASTHANNE", "ELASTHANNE", "エラスタン"])
def test_complete_elastane_language_aliases_use_spandex_key(name):
    result = parse_label(f"95% COTTON 5% {name}")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 95, "spandex": 5}


@pytest.mark.parametrize("text", [
    "100% COT\nTON / OLEFIN",
    "100% BAU\nMWOLLE / OLEFIN 10%",
    "95% COTTON\n5% ÉLASTHANN\nE / OLEFIN",
    "100% COT\nTON / UNKNOWN",
    "COTTON 95\n% OLEFIN",
])
def test_restoring_a_wrapped_alias_does_not_hide_unknown_continuations(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("text", [
    "100% POLYESTER\nA PART LA GARNITURE",
    "POLYESTER 100%\nA PART LA GARNITURE",
])
def test_a_complete_material_alias_does_not_absorb_the_next_words_first_letter(text):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}


@pytest.mark.parametrize("text", [
    "100% COT\nTON / OLEFIN\n100% COTTON / OLEFIN",
    "UK: 100% COTTON FR: 100% COTON / OLEFIN JP: 100% コットン",
])
def test_repeated_or_space_padded_translations_keep_restored_word_guards(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
