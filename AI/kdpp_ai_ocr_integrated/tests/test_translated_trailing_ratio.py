"""Explicit shared ratios may appear on the last complete translation alias."""

import pytest

from apps.text.composition_candidates import _translated_line_candidates
from apps.text.parse_label import build_line_infos, parse_label
from part_policy_assertions import assert_selected_part


@pytest.mark.parametrize("text,expected", [
    ("COTON /\nCOTTON 100%", {"cotton": 100}),
    ("COTON -\nCOTTON 100%", {"cotton": 100}),
    ("ALGODÓN /\nCOTON /\nCOTTON 100%", {"cotton": 100}),
    ("ALGODÃO /\nCOTON\nCOTTON 100%", {"cotton": 100}),
    ("COTON\nALGODÓN /\nCOTTON 100%", {"cotton": 100}),
    ("MERCERIZED COTTON /\nCOTTON 100%", {"cotton": 100}),
    ("ポリエステル /\nPOLYESTER 100%", {"polyester": 100}),
    ("棉 /\nCOTTON 100%", {"cotton": 100}),
    ("COTON /\n100% COTTON", {"cotton": 100}),
    ("COTON /\nCOTTON 100% /\nALGODÓN", {"cotton": 100}),
    (
        "COTON /\nCOTTON 60%\nPOLYESTER /\nPOLIESTER 40%",
        {"cotton": 60, "polyester": 40},
    ),
    (
        "COTON /\nCOTTON 62.5%\nPOLIÉSTER /\nPOLYESTER 37.5%",
        {"cotton": 62.5, "polyester": 37.5},
    ),
    (
        "COTON /\nCOTTON 60%\n40% POLYESTER /\nPOLIÉSTER",
        {"cotton": 60, "polyester": 40},
    ),
    (
        "OUTER\nCOTON /\nCOTTON 100%\nLINING NYLON 100%",
        {"cotton": 100},
    ),
])
def test_complete_preceding_translations_share_last_alias_explicit_ratio(text, expected):
    result = parse_label(f"{text}\nHAND WASH")
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("text", [
    "COTON\nCOTTON 100%",
    "COTON /\nCOTTON .100%",
    "COTON /\nNYLON 100%",
    "COTON / OLEFIN\nCOTTON 100%",
    "COTON / UNKNOWN\nCOTTON 100%",
    "COTON /\nCOTTON 100% OLEFIN",
    "COTON /\nOLEFIN COTTON 100%",
    "COTON /\nCOTTON 100% UNKNOWN",
    "COTON /\nCOTTON 100% / NYLON",
    "COTON /\nCOTTON 100",
    "COTON /\nCOTTON -100%",
    "COTON /\nCOTTON +100%",
    "COTON /\nCOTTON 100%%",
    "COTON /\nCOTTON 130%",
    "COTON /\nCOTTON 60% 40%",
    "COTON /\nCOTTON 100%\n20%",
    "20%\nCOTON /\nCOTTON 100%",
    "COTON /\n20%\nCOTTON 100%",
    "COTON /\nSIZE\nCOTTON 100%",
    "COTON /\nMADE IN CHINA\nCOTTON 100%",
    "COTON /\nLINING COTTON 100%",
    "COTON /\nCOMPOSITION UNKNOWN\nCOTTON 100%",
    "COTON /\nCOTTON 100%\nCOTON 20%",
    "COTON /\nCOTTON 60%\nPOLYESTER /\nPOLIESTER 30%",
    "COTON /\nCOTTON 60%\nPOLYESTER /\nPOLIESTER 50%",
    "COTON /\nCOTTON 100%\nCOTTON 90% /\nSPANDEX 10%",
    "60%\nCOTON /\nCOTTON 100%\nSPANDEX 40%",
    "COTON /\nCOTTON 100%\nHAND WASH OLEFIN",
    "OLEFIN\nCOTON /\nCOTTON 100%",
    "COTON /\nCOTTON 100%\nOLEFIN",
])
def test_preceding_translations_keep_unknown_numeric_and_boundary_evidence(text):
    result = parse_label(f"{text}\nHAND WASH")
    if "LINING" in text:
        assert_selected_part(result, 'lining', {'cotton': 100}, unconfirmed='generic')
        return
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_trailing_ratio_candidate_covers_original_alias_rows_without_duplicate_numbers():
    text = "COTON /\nCOTTON 60%\nPOLYESTER /\nPOLIESTER 40%\nHAND WASH"
    infos = build_line_infos(text)
    candidates = _translated_line_candidates(infos)
    assert any(candidate.row_indices == (0, 1, 2, 3) for candidate in candidates)
    assert all(candidate.materials == {"cotton": 60, "polyester": 40}
               for candidate in candidates)
    assert [info.raw for info in infos[:4]] == [
        "coton /", "cotton 60%", "polyester /", "poliester 40%",
    ]
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [60.0, 40.0]}
    assert result["parse_evidence"]["observed_materials"] == {
        "generic": ["cotton", "cotton", "polyester", "polyester"],
    }


def test_unreadable_suffix_on_shared_ratio_row_stays_in_observed_evidence():
    text = "COTON /\nCOTTON 100% OLEFIN\nHAND WASH"
    infos = build_line_infos(text)
    assert infos[1].raw == "cotton 100% olefin"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [100.0]}


@pytest.mark.parametrize("extra", ["30", "0", "0.5", "0,5", "300"])
@pytest.mark.parametrize("ratio_first", [False, True])
def test_final_translation_ratio_does_not_hide_a_bare_numeric_suffix(extra, ratio_first):
    final = f"100% COTON {extra}" if ratio_first else f"COTON 100% {extra}"
    text = f"COTTON /\n{final}\nHAND WASH"
    assert build_line_infos(text)[1].raw.endswith(extra)
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("extra", ["+30", "-30", "−30", "±30", "30%", "0%", "+", "-", "−", "±", "%"])
@pytest.mark.parametrize("ratio_first", [False, True])
def test_final_translation_ratio_keeps_signed_and_extra_percent_evidence(extra, ratio_first):
    final = f"100% COTON {extra}" if ratio_first else f"COTON 100% {extra}"
    result = parse_label(f"COTTON /\n{final}\nHAND WASH")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("sign", ["+", "-", "±", "≈", "−", "~", "∼", "≃"])
@pytest.mark.parametrize("placement", ["prefix", "before_separator"])
def test_preceding_ratio_free_alias_does_not_hide_uncertain_signs(sign, placement):
    first = f"{sign} COTTON /" if placement == "prefix" else f"COTTON {sign} /"
    result = parse_label(f"{first}\nCOTON 100%\nHAND WASH")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("sign", ["+", "±", "≈", "−"])
def test_standalone_uncertain_sign_cannot_bridge_alias_and_inline_ratio(sign):
    result = parse_label(f"COTTON /\n{sign}\nCOTON 100%\nHAND WASH")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("middle", ["+ COTON", "COTON &"])
def test_all_preceding_alias_rows_require_complete_literal_consumption(middle):
    result = parse_label(f"COTTON /\n{middle}\nALGODON 100%\nHAND WASH")
    assert result["status"] == "failed", result
    assert result["materials"] == {}
