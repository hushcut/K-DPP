"""OCR 후보의 조성 충돌을 점수로 숨기지 않는 회귀 검사."""

from io import BytesIO

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text


def run_with_payloads(monkeypatch, payloads):
    responses = iter(payloads)
    calls = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: b"preprocessed")

    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        return next(responses)

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    buffer = BytesIO()
    Image.new("RGB", (80, 80), "white").save(buffer, format="PNG")
    result = ocr_text.run_ocr_bytes(
        buffer.getvalue(),
        enable_reflection=False,
        enable_denoised=False,
        enable_rotated=False,
    )
    return result, calls


@pytest.mark.parametrize(
    ("raw", "layout"),
    [
        ("COTTON POLYESTER 80% 20%", "POLYESTER COTTON 80% 20%"),
        ("POLYESTER COTTON 80% 20%", "COTTON POLYESTER 80% 20%"),
        ("COTTON 100%", "POLYESTER 80% WOOL 20%"),
        ("OUTER COTTON 100%", "OUTER POLYESTER 80% WOOL 20%"),
    ],
)
def test_layout_conflict_fails_without_another_ocr_call(monkeypatch, raw, layout):
    result, calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout)])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["error_code"] == "ambiguous_composition"
    assert analysis["materials"] == {}
    assert analysis["confidence"] == {"ocr": "low", "parser": "low"}
    assert analysis["ocr"]["conflicting_parts"]
    assert any("ambiguous_composition_candidates" in item for item in analysis["warnings"])
    assert len(calls) == result.metadata.candidate_count == 1


def test_preprocessed_conflict_cannot_replace_a_complete_original(monkeypatch):
    result, calls = run_with_payloads(
        monkeypatch,
        ["COTTON\n80%\nPOLYESTER\n20%", "COTTON 20% POLYESTER 80%"],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["ocr"]["conflicting_parts"] == ["generic"]
    assert len(calls) == result.metadata.candidate_count == 2


@pytest.mark.parametrize(
    ("raw", "layout"),
    [
        ("COTTON 100%\nPOLYESTER 100%", "COTTON 100%"),
        ("COTTON 100%", "COTTON 100%\nPOLYESTER 100%"),
    ],
)
def test_existing_parser_conflict_is_not_erased_by_a_simpler_candidate(
    monkeypatch, raw, layout,
):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout)])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["error_code"] == "ambiguous_composition"
    assert analysis["materials"] == {}


def test_preprocessing_cannot_erase_a_confirmed_original_conflict(monkeypatch):
    result, calls = run_with_payloads(
        monkeypatch, ["COTTON 100%\nPOLYESTER 100%", "COTTON 100%"],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert len(calls) == 2


def test_failed_candidates_preserve_the_detected_conflict(monkeypatch):
    result, _calls = run_with_payloads(
        monkeypatch, ["COTTON 100%\nPOLYESTER 100%", "BRAND AND SIZE ONLY"],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["error_code"] == "ambiguous_composition"
    assert analysis["materials"] == {}
    assert analysis["confidence"] == {"ocr": "low", "parser": "low"}


def test_extra_ratio_in_preprocessing_cannot_be_hidden_by_successful_original(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [
        "LYOCELL\n50%\nNYLON\n45%\nPOLYURETHANE\n5%",
        "LYOCELL 50% NYLON 45% POLYURETHANE 5%\n57%",
    ])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["ocr"]["unpaired_ratio_parts"] == ["generic"]


@pytest.mark.parametrize(
    ("raw", "complete", "part"),
    [
        ("COTTON 100%\n50", "COTTON 100%", "generic"),
        ("COTTON 100%\n100", "COTTON 100%", "generic"),
        ("COMPOSITION\nCOTTON 95% SPANDEX 5%\n50,5",
         "COMPOSITION\nCOTTON 95% SPANDEX 5%", "generic"),
        ("OUTER COTTON 100%\n50", "OUTER COTTON 100%", "outer"),
    ],
)
@pytest.mark.parametrize("source", ["layout", "preprocessed"])
def test_candidate_cannot_discard_unpaired_numbers_without_percent(
    monkeypatch, raw, complete, part, source,
):
    payloads = (
        [ocr_text.OcrPayload(raw, complete), ocr_text.OcrPayload("SIZE M")]
        if source == "layout" else [raw, complete]
    )
    result, calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["ocr"]["unpaired_ratio_parts"] == [part]
    assert analysis["confidence"] == {"ocr": "low", "parser": "low"}
    assert len(calls) == 2


@pytest.mark.parametrize("metadata", ["SIZE\n50", "RN 12345"])
def test_metadata_numbers_do_not_create_unpaired_ratio_evidence(monkeypatch, metadata):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        f"COTTON 100%\n{metadata}", "COTTON 100%",
    )])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["ocr"]["unpaired_ratio_parts"] == []


def test_duplicate_unpaired_ratio_requires_another_consumed_occurrence(monkeypatch):
    result, calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "COTTON 100%\n100%", "COTTON 100%",
    ), ocr_text.OcrPayload("SIZE M")])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("raw", "layout", "expected"),
    [
        ("COTTON 100%\n100%", "COTTON 100%\n면 100%", {"cotton": 100}),
        ("COTTON 100%\n100", "COTTON 100%\n면 100%", {"cotton": 100}),
        ("COTTON 95% SPANDEX 5%\n100",
         "겉감 면 100%\n배색 면 95% 폴리우레탄 5%", {"cotton": 100}),
        ("COTTON 95% SPANDEX 5%\n100%",
         "겉감 면 100%\n배색 면 95% 폴리우레탄 5%", {"cotton": 100}),
    ],
)
def test_layout_can_resolve_all_observed_ratios_without_discarding_them(
    monkeypatch, raw, layout, expected,
):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout)])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == expected
    assert analysis["ocr"]["unpaired_ratio_parts"] == []


def test_text_only_compatibility_wrapper_also_rejects_extra_ratios(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [
        "LYOCELL\n50%\nNYLON\n45%\nPOLYURETHANE\n5%",
        "LYOCELL 50% NYLON 45% POLYURETHANE 5%\n57%",
    ])
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    with pytest.raises(ocr_text.OcrError):
        ocr_text.run_ocr("unused-label.png")


@pytest.mark.parametrize(
    ("raw", "layout", "expected"),
    [
        ("COTTON 80% POLYESTER 20%", "POLYESTER 20% COTTON 80%",
         {"cotton": 80, "polyester": 20}),
        ("COTTON 98% ELASTANE 2%", "棉 98% 氨纶 2%",
         {"cotton": 98, "spandex": 2}),
        ("OUTER COTTON 100%", "LINING POLYESTER 100%", {"cotton": 100}),
        ("BRAND AND SIZE ONLY", "COTTON 100%", {"cotton": 100}),
    ],
)
def test_equivalent_separate_or_failed_candidates_do_not_block_success(
    monkeypatch, raw, layout, expected,
):
    result, calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout)])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == expected
    assert analysis["ocr"]["conflicting_parts"] == []
    assert len(calls) == 1


def test_polyurethane_and_spandex_ocr_candidates_conflict(monkeypatch):
    result, calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "COTTON 98% POLYURETHANE 2%", "棉 98% 氨纶 2%",
    )])
    analysis = analyze_ocr_result(result)
    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["ocr"]["conflicting_parts"] == ["generic"]
    assert len(calls) == 1


def test_lining_conflict_does_not_invalidate_an_agreed_outer(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "OUTER COTTON 100%\nLINING POLYESTER 100%",
        "OUTER COTTON 100%\nLINING WOOL 100%",
    )])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["parts"] == {"outer": {"cotton": 100}}
    assert analysis["ocr"]["conflicting_parts"] == ["lining"]
    assert "lining:ambiguous_composition_candidates" in analysis["warnings"]


def test_outer_conflict_keeps_confirmed_lining_and_outer_evidence(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "OUTER COTTON 100%\nLINING POLYESTER 100%",
        "OUTER WOOL 100%\nLINING POLYESTER 100%",
    )])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["selected_part"] == "lining"
    assert analysis["materials"] == {"polyester": 100}
    assert "outer" not in analysis["parts"]
    assert "outer:ambiguous_composition_candidates" in analysis["warnings"]


def test_text_only_compatibility_wrapper_rejects_representative_conflict(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "COTTON 100%", "POLYESTER 100%",
    )])
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    with pytest.raises(ocr_text.OcrError, match="조성"):
        ocr_text.run_ocr("unused-label.png")


def test_text_only_compatibility_wrapper_preserves_agreed_outer(monkeypatch):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "OUTER COTTON 100%\nLINING POLYESTER 100%",
        "OUTER COTTON 100%\nLINING WOOL 100%",
    )])
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    assert ocr_text.run_ocr("unused-label.png") == result.text

@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "alternative", "layout_calls"),
    [
        ("COTTON 100%\nOLEFIN 50%", "COTTON 100%", 1),
        ("COTTON 100%\nMODACRYLIC 50%", "COTTON 100%", 1),
        ("COTTON 100%\nPOLYESTER -5%", "COTTON 100%", 1),
        ("COTTON 100%\nPOLYESTER 0%", "COTTON 100%", 1),
        ("COTTON 100%\nPOLYESTER 101%", "COTTON 100%", 1),
        ("COTTON 100%\nPOLYESTER 1..5%", "COTTON 100%", 1),
        ("COTTON 100%\nPOLYESTER", "COTTON 100%", 2),
        ("COTTON 80%\nPOLYESTER", "COTTON 100%", 2),
        ("COTTON 100%\nPOLYESTER 50%", "COTTON 100%", 2),
        ("COTTON 100%\nMODACRYLIC 100%", "COTTON 100%\n면 100%", 1),
        ("IMITATION LEATHER 100%", "LEATHER 100%", 1),
        ("OUTER COTTON 100%\nOUTER OLEFIN 50%", "OUTER COTTON 100%", 1),
        ("OUTER POLYESTER\nLINING COTTON 100%", "LINING COTTON 100%", 2),
        ("COTTON 100%\nOLEFIN 50%", "OUTER COTTON 100%", 1),
        ("COTTON 80%\nPOLYESTER", "COTTON 80% SPANDEX 20%", 2),
        ("COTTON 80%\nPOLYESTER", "COTTON 20% POLYESTER 80%", 2),
        ("COTTON 100%\nPOLYESTER\nPOLYESTER",
         "OUTER COTTON 100%\nLINING POLYESTER 100%", 2),
    ],
)
def test_rejected_composition_cannot_disappear_in_another_candidate(
    monkeypatch, source, raw, alternative, layout_calls,
):
    payloads = (
        [ocr_text.OcrPayload(raw, alternative), ocr_text.OcrPayload("SIZE M")]
        if source == "layout"
        else [ocr_text.OcrPayload(raw, ""), ocr_text.OcrPayload(alternative, "")]
    )
    result, calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    if raw == "OUTER POLYESTER\nLINING COTTON 100%":
        assert analysis["status"] == "success"
        assert analysis["selected_part"] == "lining"
        assert analysis["materials"] == {"cotton": 100}
        assert "outer" not in analysis["parts"]
        assert analysis["ocr"]["rejected_composition_parts"]["outer"]
        assert len(calls) == 2
        return
    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["confidence"]["ocr"] == "low"
    assert analysis["ocr"]["rejected_composition_parts"]
    assert analysis["parse_evidence"]["rejected_composition_parts"]
    assert len(calls) == (layout_calls if source == "layout" else 2)


@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "alternative", "expected"),
    [
        ("COTTON 80%\nPOLYESTER", "COTTON 80% POLYESTER 20%",
         {"cotton": 80, "polyester": 20}),
        ("COTTON POLYESTER", "COTTON 80% POLYESTER 20%",
         {"cotton": 80, "polyester": 20}),
        ("OUTER COTTON\nLINING POLYESTER 100%",
         "OUTER COTTON 100%\nLINING POLYESTER 100%", {"cotton": 100}),
        ("COTTON 80%\nELASTANE", "면 80% SPANDEX 20%",
         {"cotton": 80, "spandex": 20}),
        ("COTTON 100%\nPOLYESTER",
         "OUTER COTTON 100%\nLINING POLYESTER 100%", {"cotton": 100}),
    ],
)
def test_complete_material_and_ratio_recovery_is_allowed(
    monkeypatch, source, raw, alternative, expected,
):
    payloads = (
        [ocr_text.OcrPayload(raw, alternative)]
        if source == "layout"
        else [ocr_text.OcrPayload(raw, ""), ocr_text.OcrPayload(alternative, "")]
    )
    result, _calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == expected
    assert analysis["ocr"]["rejected_composition_parts"] == {}


@pytest.mark.parametrize(
    ("raw", "alternative", "reason"),
    [
        ("OUTER COTTON 100%\nLINING MODACRYLIC 50%",
         "OUTER COTTON 100%\nLINING POLYESTER 100%", "unresolved_material_token"),
        ("OUTER COTTON 100%\nLINING POLYESTER -5%",
         "OUTER COTTON 100%\nLINING POLYESTER 100%", "invalid_ratio"),
        ("OUTER COTTON 100%\nLINING POLYESTER",
         "OUTER COTTON 100%", "unpaired_material_rows"),
    ],
)
def test_lower_priority_rejections_preserve_the_confirmed_outer(
    monkeypatch, raw, alternative, reason,
):
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(raw, alternative)],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["selected_part"] == "outer"
    assert analysis["parts"] == {"outer": {"cotton": 100}}
    assert reason in analysis["ocr"]["rejected_composition_parts"]["lining"]
    assert f"lining:{reason}" in analysis["warnings"]


@pytest.mark.parametrize(
    "row", ["OLEFIN 50%", "POLYESTER -5%", "POLYESTER"],
)
def test_text_wrapper_rejects_disappearing_composition_evidence(monkeypatch, row):
    result, _calls = run_with_payloads(
        monkeypatch, [
            ocr_text.OcrPayload(f"COTTON 100%\n{row}", "COTTON 100%"),
            ocr_text.OcrPayload("SIZE M"),
        ],
    )
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    with pytest.raises(ocr_text.OcrCompositionError):
        ocr_text.run_ocr("unused.png")


def test_text_wrapper_keeps_confirmed_outer_with_rejected_lining(monkeypatch):
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(
            "OUTER COTTON 100%\nLINING POLYESTER -5%", "OUTER COTTON 100%",
        )],
    )
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    assert ocr_text.run_ocr("unused.png") == result.text

@pytest.mark.parametrize("row", ["OLEFIN 50%", "POLYESTER -5%", "POLYESTER"])
def test_rejections_are_preserved_when_the_original_is_the_successful_candidate(
    monkeypatch, row,
):
    result, calls = run_with_payloads(
        monkeypatch, [
            ocr_text.OcrPayload("COTTON 100%", f"COTTON 100%\n{row}"),
            ocr_text.OcrPayload("SIZE M"),
        ],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["ocr"]["source"] == "original"
    assert len(calls) == (2 if row == "POLYESTER" else 1)

@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "alternative", "reason"),
    [
        ("COTTON 100%\nOLEFIN 50%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
         "unresolved_material_token"),
        ("COTTON 100%\nMODACRYLIC 50%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
         "unresolved_material_token"),
        ("COTTON 100%\nPOLYESTER -5%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%", "invalid_ratio"),
        ("COTTON 100%\nPOLYESTER 0%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%", "invalid_ratio"),
        ("COTTON 100%\nPOLYESTER 101%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%", "invalid_ratio"),
        ("COTTON 100%\nPOLYESTER 1..5%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
         "invalid_composition_evidence"),
        ("COTTON 100%\nPOLYESTER\n50%",
         "OUTER COTTON 100%\nLINING RAYON 50% NYLON 50%",
         "unpaired_material_rows"),
        ("COTTON 50% NYLON 50%\nOLEFIN 50%\n50%",
         "COTTON 50% NYLON 50%\n면 50% 나일론 50%",
         "unresolved_material_token"),
        ("IMITATION LEATHER 100%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
         "invalid_composition_evidence"),
    ],
)
def test_resolved_orphan_ratios_cannot_erase_independent_rejections(
    monkeypatch, source, raw, alternative, reason,
):
    payloads = (
        [ocr_text.OcrPayload(raw, alternative), ocr_text.OcrPayload("SIZE M")]
        if source == "layout"
        else [ocr_text.OcrPayload(raw, ""), ocr_text.OcrPayload(alternative, "")]
    )
    result, calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
    assert analysis["confidence"]["ocr"] == "low"
    assert analysis["ocr"]["unpaired_ratio_parts"] == []
    assert reason in analysis["ocr"]["rejected_composition_parts"]["generic"]
    assert reason in analysis["parse_evidence"]["rejected_composition_parts"]["generic"]
    assert len(calls) == (
        2 if source == "preprocessed" or reason == "unpaired_material_rows" else 1
    )


@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "alternative"),
    [
        ("COTTON 100%\nPOLYESTER\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%"),
        ("COTTON 100%\n50%\n50%",
         "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%"),
    ],
)
def test_orphan_recovery_preserving_material_evidence_still_succeeds(
    monkeypatch, source, raw, alternative,
):
    payloads = (
        [ocr_text.OcrPayload(raw, alternative)]
        if source == "layout"
        else [ocr_text.OcrPayload(raw, ""), ocr_text.OcrPayload(alternative, "")]
    )
    result, _calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["ocr"]["unpaired_ratio_parts"] == []
    assert analysis["ocr"]["rejected_composition_parts"] == {}


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("OLEFIN 50%", "unresolved_material_token"),
        ("POLYESTER -5%", "invalid_ratio"),
    ],
)
def test_combined_lining_rejections_preserve_confirmed_outer(monkeypatch, row, reason):
    raw = f"OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%\n{row}\n50%"
    alternative = (
        "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%\n"
        "폴리에스터 50% 나일론 50%"
    )
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(raw, alternative)],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["parts"] == {"outer": {"cotton": 100}}
    assert analysis["ocr"]["unpaired_ratio_parts"] == []
    assert reason in analysis["ocr"]["rejected_composition_parts"]["lining"]
    assert f"lining:{reason}" in analysis["warnings"]


@pytest.mark.parametrize("row", ["OLEFIN 50%", "POLYESTER -5%"])
def test_text_wrapper_rejects_combined_rejections_after_ratio_recovery(monkeypatch, row):
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(
            f"COTTON 100%\n{row}\n50%",
            "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
        )],
    )
    monkeypatch.setattr(ocr_text, "run_ocr_with_metadata", lambda *_args: result)

    with pytest.raises(ocr_text.OcrCompositionError):
        ocr_text.run_ocr("unused.png")


@pytest.mark.parametrize("row", ["OLEFIN 50%", "POLYESTER -5%"])
def test_combined_rejections_are_preserved_when_the_original_is_successful(
    monkeypatch, row,
):
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(
            "OUTER COTTON 100%\nLINING POLYESTER 50% NYLON 50%",
            f"COTTON 100%\n{row}\n50%",
        )],
    )
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["ocr"]["source"] == "original"
    assert analysis["ocr"]["unpaired_ratio_parts"] == []


@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "complete", "expected"),
    [
        ("SHELL:COTTON\nCOTTON\n100%", "SHELL:COTTON\n100%", {"cotton": 100}),
        ("OUTER\nCOTTON\nCOTTON\n100%", "OUTER COTTON 100%", {"cotton": 100}),
        ("SHELL:\nCOTTON\nCOTTON\n100%", "OUTER COTTON 100%", {"cotton": 100}),
        ("겉감 면\n면\n100%", "겉감 면 100%", {"cotton": 100}),
        ("OUTER COTTON\n면\n100%", "OUTER COTTON 100%", {"cotton": 100}),
        ("OUTER POLYURETHANE\n폴리우레탄\n100%",
         "OUTER POLYURETHANE 100%", {"polyurethane": 100}),
    ],
)
def test_adjacent_duplicate_material_rows_can_use_a_confirmed_same_part(
    monkeypatch, source, raw, complete, expected,
):
    payloads = (
        [ocr_text.OcrPayload(raw, complete), "SIZE M"]
        if source == "layout" else [raw, complete]
    )
    result, _calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["selected_part"] == "outer"
    assert analysis["materials"] == expected
    assert analysis["ocr"]["rejected_composition_parts"] == {}


def test_preprocessed_duplicate_does_not_invalidate_a_confirmed_original_outer(monkeypatch):
    original = "SHELL:COTTON\n100%\nLINING:POLYESTER\nCOTTON"
    preprocessed = "SHELL:COTTON\nCOTTON\n100%\nLINING:POLYESTER\nCOTTON"
    result, calls = run_with_payloads(monkeypatch, [original, preprocessed])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["selected_part"] == "outer"
    assert analysis["ocr"]["source"] == "original"
    assert "outer" not in analysis["ocr"]["rejected_composition_parts"]
    assert "lining" in analysis["ocr"]["rejected_composition_parts"]
    assert len(calls) == 2


@pytest.mark.parametrize("source", ["layout", "preprocessed"])
@pytest.mark.parametrize(
    ("raw", "complete"),
    [
        ("COTTON\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n50%\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON 100%\nCOTTON", "OUTER COTTON 100%"),
        ("OUTER COTTON\nFABRIC2\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nSIZE M\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nOUTER COTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER1 COTTON\nOUTER2 COTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n80%\nPOLYESTER\n20%",
         "OUTER COTTON 80% POLYESTER 20%"),
        ("OUTER COTTON\nCOTTON\n100%\nOLEFIN 50%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nOLEFIN", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nMODACRYLIC", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nUNKNOWN", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nUNKNOWN100", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nFABRIC2", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%\nSECOND FABRIC", "OUTER COTTON 100%"),
        ("OUTER UNKNOWN\nCOTTON\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER OLEFIN\nCOTTON\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER 50\nCOTTON\nCOTTON\n100%", "OUTER COTTON 100%"),
        ("OUTER COTTON\nCOTTON\n100%", "OUTER POLYESTER 100%"),
        ("OUTER POLYURETHANE\nPOLYURETHANE\n100%", "OUTER SPANDEX 100%"),
    ],
)
def test_duplicate_material_recovery_cannot_hide_other_composition_evidence(
    monkeypatch, source, raw, complete,
):
    payloads = (
        [ocr_text.OcrPayload(raw, complete), "SIZE M"]
        if source == "layout" else [raw, complete]
    )
    result, _calls = run_with_payloads(monkeypatch, payloads)
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}


def test_preprocessed_layout_heading_and_duplicate_keep_confirmed_original(monkeypatch):
    original = ocr_text.OcrPayload(
        "SHELL:COTTON\n100%\nLINING:POLYESTER65%\nCOTTON\n35%\n30",
        "SHELL:COTTON\nLINING:POLYESTER100%\nCOTTON65%\n35%\n30",
    )
    preprocessed = ocr_text.OcrPayload(
        "SHELL:COTTON\nCOTTON\n100%\nLINING:POLYESTER65%\nCOTTON\n35%\n30",
        "SHELL LINING:COTTON COTTON\nPOLYESTER100%\nCOTTON65%\n35%\n30",
    )
    result, calls = run_with_payloads(monkeypatch, [original, preprocessed])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["selected_part"] == "outer"
    assert "outer" not in analysis["ocr"]["rejected_composition_parts"]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "heading", ["OUTER", "SHELL", "겉감", "SHELL:", "(OUTER)"],
)
def test_empty_layout_heading_can_recover_only_its_confirmed_same_part(monkeypatch, heading):
    result, _calls = run_with_payloads(monkeypatch, [ocr_text.OcrPayload(
        "OUTER COTTON 100%\nLINING POLYESTER 100%",
        f"{heading}\nLINING POLYESTER 100%",
    )])
    analysis = analyze_ocr_result(result)

    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["ocr"]["rejected_composition_parts"] == {}


@pytest.mark.parametrize(
    ("raw", "layout"),
    [
        ("LINING POLYESTER 100%", "OUTER\nLINING POLYESTER 100%"),
        ("OUTER\nLINING POLYESTER 100%", "OUTER COTTON 100%"),
        ("OUTER COTTON 100%", "OUTER\nUNKNOWN\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER\nOLEFIN\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER\n50%\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER\nFABRIC2\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER\nOUTER\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER UNKNOWN\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER OLEFIN\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER BROADCLOTH\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER LUREX\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER FABRIC2\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER SECOND FABRIC\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER SPECIAL\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER 50\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "OUTER100\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "SHELL2\nLINING POLYESTER 100%"),
        ("OUTER COTTON 100%", "겉감 미확인소재\n안감 폴리에스터100%"),
    ],
)
def test_empty_heading_recovery_cannot_erase_raw_or_other_part_evidence(
    monkeypatch, raw, layout,
):
    result, _calls = run_with_payloads(
        monkeypatch, [ocr_text.OcrPayload(raw, layout), "SIZE M"],
    )
    analysis = analyze_ocr_result(result)

    if raw == "LINING POLYESTER 100%":
        assert analysis["status"] == "success"
        assert analysis["selected_part"] == "lining"
        assert analysis["materials"] == {"polyester": 100}
        assert "outer" not in analysis["parts"]
        assert analysis["ocr"]["rejected_composition_parts"]["outer"]
        return
    assert analysis["status"] == "failed"
    assert analysis["materials"] == {}
