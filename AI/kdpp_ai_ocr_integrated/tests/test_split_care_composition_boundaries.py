"""A complete split care sentence may bound restored fiber evidence."""

import pytest

from apps.text.parse_label import parse_label


COMPOSITIONS = [
    ("polyester 95\nspan 5\n%", {"polyester": 95, "spandex": 5}),
    ("COTTON 80\nNYLON 20\n%", {"cotton": 80, "nylon": 20}),
    ("WOOL 62.5\nNYLON 37.5\n%", {"wool": 62.5, "nylon": 37.5}),
]


def test_full_label_split_dry_cleaning_boundary_preserves_literal_ratios():
    text = "Gum\nmade in korea\nDRY CLEANING\nONLY\npolyester 95\nspan 5\n%"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 95, "spandex": 5}
    assert result["selected_part"] == "generic"
    assert result["parse_evidence"]["observed_ratios"] == {"generic": [95.0, 5.0]}
    assert result["parse_evidence"]["paired_material_ratios"] == {
        "generic": [["polyester", 95.0], ["spandex", 5.0]],
    }
    assert result["raw_ocr_preview"] == " ".join(text.split())


@pytest.mark.parametrize("composition,expected", COMPOSITIONS)
@pytest.mark.parametrize("care", [
    "DRY CLEANING\nONLY",
    "DRY CLEAN\nONLY",
    "DO NOT\nBLEACH",
    "HAND\nWASH",
    "MACHINE\nWASH COLD",
])
@pytest.mark.parametrize("before", [True, False])
def test_complete_known_split_care_bounds_an_arbitrary_composition(composition, expected, care, before):
    text = f"{care}\n{composition}" if before else f"{composition}\n{care}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("care", [
    "ONLY",
    "CLEANING\nONLY",
    "DRY\nONLY",
    "NOT\nBLEACH",
    "WASHLIKE\nONLY",
    "DRY CLEANING\nOLEFIN\nONLY",
    "DRY CLEANING\nUNKNOWN\nONLY",
    "DRY CLEANING\nUNRECOGNIZED\nONLY",
    "DRY CLEANING\nCOTTON\nONLY",
    "DRY CLEANING\n20\nONLY",
    "DRY CLEANING\n0\nONLY",
    "DRY CLEANING\n10%\nONLY",
    "DRY CLEANING\n+\nONLY",
    "DRY CLEANING\n±\nONLY",
    "DRY CLEANING\nONLY UNKNOWN",
    "DRY CLEANING\nONLY OLEFIN",
    "DRY CLEANING\nONLY 20",
    "DRY CLEANING\nONLY 10%",
    "DRY CLEANING\nONLY ±",
    "DRY CLEANING\nONLY ~",
    "DRY CLEANING 20\nONLY",
    "DRY CLEANING 10%\nONLY",
    "DRY CLEANING +\nONLY",
])
def test_incomplete_care_and_intervening_evidence_do_not_bound_a_restored_block(care):
    result = parse_label(f"{care}\npolyester 95\nspan 5\n%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("extra", [
    "OLEFIN", "UNKNOWN", "UNRECOGNIZED", "COTTON",
    "10%", "20", "0", "00", "-0", "0%", "0.5", "300", "+20", "-20", "±", "~", "SPANDEX 10%",
])
@pytest.mark.parametrize("before", [True, False])
def test_split_care_does_not_hide_an_extra_fiber_ratio_or_qualifier(extra, before):
    composition = "polyester 95\nspan 5\n%"
    text = (
        f"{extra}\n{composition}\nDRY CLEANING\nONLY"
        if before else f"DRY CLEANING\nONLY\n{composition}\n{extra}"
    )
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("care", [
    "DRY CLEANING\nLINING ONLY",
    "DRY CLEANING\nOUTER ONLY",
    "DRY CLEANING\nSIZE\nONLY",
    "DRY CLEANING\nCOMPOSITION UNKNOWN\nONLY",
])
def test_a_different_part_or_field_does_not_complete_the_care_phrase(care):
    result = parse_label(f"{care}\npolyester 95\nspan 5\n%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("polyester,span", [(96, 5), (95, 6), (95, 4), (94, 5)])
def test_split_care_never_repairs_a_noncomplete_ratio_total(polyester, span):
    result = parse_label(f"DRY CLEANING\nONLY\npolyester {polyester}\nspan {span}\n%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("extra", ["0", "00", "-0", "0%"])
def test_another_success_candidate_does_not_erase_an_independent_numeric_rejection(extra):
    from apps.service.label_analysis import analyze_ocr_result
    from apps.text.ocr_text import OcrMetadata, OcrResult, _assess_candidates, _build_candidate

    text = "DRY CLEANING\nONLY\npolyester 95\nspan 5\n%"
    original = _build_candidate("original", text)
    additional = _build_candidate("preprocessed", f"{text}\n{extra}")
    assert original.parser_status == "success"
    assert additional.parser_status == "failed"
    assert "invalid_composition_evidence" in additional.rejected_composition_parts["generic"]

    decision = _assess_candidates([original, additional])
    assert decision.best.materials == {"polyester": 95, "spandex": 5}
    assert decision.status == "failed"
    assert "invalid_composition_evidence" in decision.rejected_composition_parts["generic"]

    result = analyze_ocr_result(OcrResult(
        text=decision.best.text,
        metadata=OcrMetadata(
            source=decision.best.source,
            confidence="low",
            candidate_count=2,
            image_format="PNG",
            width=100,
            height=50,
            conflicting_parts=decision.conflicting_parts,
            unpaired_ratio_parts=decision.unpaired_ratio_parts,
            rejected_composition_parts=decision.rejected_composition_parts,
        ),
    ))
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert "invalid_composition_evidence" in result["parse_evidence"]["rejected_composition_parts"]["generic"]
    assert "invalid_composition_evidence" in result["ocr"]["rejected_composition_parts"]["generic"]
    assert result["ocr"]["external_call_count"] == 0


@pytest.mark.parametrize("extra", ["UNKNOWN", "~", "0\nUNKNOWN"])
@pytest.mark.parametrize("before", [True, False])
@pytest.mark.parametrize("reverse_candidates", [True, False])
def test_matching_candidate_cannot_erase_split_care_context_rejection(extra, before, reverse_candidates):
    composition = "polyester 95\nspan 5\n%"
    text = f"{composition}\nDRY CLEANING\nONLY" if before else f"DRY CLEANING\nONLY\n{composition}"
    additional = f"{extra}\n{text}" if before else f"{text}\n{extra}"
    _assert_context_rejection_survives(text, additional, reverse_candidates)


@pytest.mark.parametrize("extra", ["٠", "０", "UNKNOWN\n٠"])
@pytest.mark.parametrize("before", [True, False])
def test_unicode_decimal_context_is_not_hidden_by_matching_candidate(extra, before):
    composition = "polyester 95\nspan 5\n%"
    text = f"{composition}\nDRY CLEANING\nONLY" if before else f"DRY CLEANING\nONLY\n{composition}"
    additional = f"{extra}\n{text}" if before else f"{text}\n{extra}"
    _assert_context_rejection_survives(text, additional, False)


@pytest.mark.parametrize("before", [True, False])
def test_unread_printed_row_with_split_care_keeps_independent_rejection(before):
    composition = "polyester 95\nspan 5\n%"
    unread = "polyester 95 UNKNOWN\nspan 5\n%"
    care = "DRY CLEANING\nONLY"
    text = f"{care}\n{composition}" if before else f"{composition}\n{care}"
    additional = f"{care}\n{unread}" if before else f"{unread}\n{care}"
    _assert_context_rejection_survives(text, additional, False)


def _assert_context_rejection_survives(text, additional_text, reverse_candidates):
    from apps.service.label_analysis import analyze_ocr_result
    from apps.text.ocr_text import OcrMetadata, OcrResult, _assess_candidates, _build_candidate

    original = _build_candidate("original", text)
    additional = _build_candidate("preprocessed", additional_text)
    assert original.parser_status == "success"
    assert additional.parser_status == "failed"
    assert "invalid_composition_evidence" in additional.rejected_composition_parts["generic"]

    candidates = [additional, original] if reverse_candidates else [original, additional]
    decision = _assess_candidates(candidates)
    assert decision.status == "failed"
    assert "invalid_composition_evidence" in decision.rejected_composition_parts["generic"]

    response = analyze_ocr_result(OcrResult(
        text=decision.best.text,
        metadata=OcrMetadata(
            source=decision.best.source,
            confidence="low",
            candidate_count=2,
            image_format="PNG",
            width=100,
            height=50,
            conflicting_parts=decision.conflicting_parts,
            unpaired_ratio_parts=decision.unpaired_ratio_parts,
            rejected_composition_parts=decision.rejected_composition_parts,
        ),
    ))
    assert response["status"] == "failed", response
    assert response["materials"] == {}
    assert "invalid_composition_evidence" in response["parse_evidence"]["rejected_composition_parts"]["generic"]
    assert "invalid_composition_evidence" in response["ocr"]["rejected_composition_parts"]["generic"]
    assert response["ocr"]["external_call_count"] == 0


@pytest.mark.parametrize("suffix", ["", "SIZE: L", "MADE IN KOREA", "LINING UNKNOWN"])
def test_known_boundaries_and_unread_lower_priority_parts_remain_confirmed(suffix):
    from apps.text.ocr_text import _assess_candidates, _build_candidate

    text = "OUTER\nDRY CLEANING\nONLY\npolyester 95\nspan 5\n%"
    original = _build_candidate("original", text)
    additional = _build_candidate("preprocessed", f"{text}\n{suffix}")
    decision = _assess_candidates([original, additional])
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 95, "spandex": 5}
    assert not decision.rejected_composition_parts.get("outer")
