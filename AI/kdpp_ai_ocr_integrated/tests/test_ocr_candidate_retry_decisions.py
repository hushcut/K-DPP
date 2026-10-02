"""최종 조성 판정에 따른 후보 재시도를 실제 Vision 없이 검증한다."""

from types import SimpleNamespace

import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text


INCOMPLETE = ocr_text.OcrPayload("COTTON 100%\nPOLYESTER", "COTTON 100%")
TRUNCATED = ocr_text.OcrPayload("COTTON 100%")
RESTORED = ocr_text.OcrPayload("OUTER COTTON 100%\nLINING POLYESTER 100%")


def run_candidates(monkeypatch, responses, **options):
    calls = []
    monkeypatch.setattr(
        ocr_text, "validate_image_bytes",
        lambda *_args, **_kwargs: ocr_text.ValidatedImage(b"original", "PNG", 100, 100),
    )
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    for name, content in (
        ("preprocess_image_bytes", b"basic"),
        ("preprocess_reflection_image_bytes", b"reflection"),
        ("preprocess_denoised_image_bytes", b"denoised"),
        ("preprocess_rotated_image_bytes", b"rotated"),
    ):
        monkeypatch.setattr(ocr_text, name, lambda _, value=content: value)

    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        assert content in responses, f"예상하지 않은 후보 호출: {content!r}"
        response = responses[content]
        if isinstance(response, Exception):
            raise response
        return response() if callable(response) else response

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    settings = {
        "enable_reflection": False, "enable_denoised": False, "enable_rotated": False,
    }
    settings.update(options)
    return ocr_text.run_ocr_bytes(b"image", **settings), calls


@pytest.mark.parametrize(
    ("original", "restored", "materials"),
    [
        (INCOMPLETE, RESTORED, {"cotton": 100}),
        (ocr_text.OcrPayload(
            "OUTER POLYESTER\nLINING COTTON 100%", "LINING COTTON 100%",
         ), ocr_text.OcrPayload(
            "OUTER POLYESTER 100%\nLINING COTTON 100%",
         ), {"polyester": 100}),
    ],
)
def test_final_rejection_triggers_basic_recovery(monkeypatch, original, restored, materials):
    result, calls = run_candidates(
        monkeypatch, {b"original": original, b"basic": restored},
    )
    analysis = analyze_ocr_result(result)

    assert calls == [b"original", b"basic"]
    assert analysis["status"] == "success"
    assert analysis["materials"] == materials
    assert analysis["ocr"]["source"] == "preprocessed"
    assert analysis["ocr"]["rejected_composition_parts"] == {}


@pytest.mark.parametrize("source", ["reflection", "denoised", "rotated"])
def test_enabled_candidate_recovers_after_individual_success_is_rejected(monkeypatch, source):
    result, calls = run_candidates(
        monkeypatch,
        {b"original": INCOMPLETE, b"basic": TRUNCATED, source.encode(): RESTORED},
        **{f"enable_{source}": True},
    )
    analysis = analyze_ocr_result(result)

    assert calls == [b"original", b"basic", source.encode()]
    assert analysis["status"] == "success"
    assert analysis["ocr"]["source"] == source
    assert analysis["ocr"]["external_call_count"] == 3


@pytest.mark.parametrize("source", ["reflection", "denoised", "rotated"])
def test_candidate_chain_stops_after_final_success(monkeypatch, source):
    order = [b"original", b"basic", b"reflection", b"denoised", b"rotated"]
    responses = {key: TRUNCATED for key in order}
    responses[b"original"] = INCOMPLETE
    responses[source.encode()] = RESTORED
    result, calls = run_candidates(
        monkeypatch, responses,
        enable_reflection=True, enable_denoised=True, enable_rotated=True,
    )

    assert calls == order[:order.index(source.encode()) + 1]
    assert analyze_ocr_result(result)["status"] == "success"
    assert result.metadata.source == source


@pytest.mark.parametrize(
    "original",
    [
        ocr_text.OcrPayload("COTTON 100%", "면 100%"),
        ocr_text.OcrPayload(
            "OUTER COTTON 100%\nLINING OLEFIN 50%", "OUTER COTTON 100%",
        ),
    ],
)
def test_confirmed_representative_skips_all_extra_candidates(monkeypatch, original):
    result, calls = run_candidates(
        monkeypatch, {b"original": original},
        enable_reflection=True, enable_denoised=True, enable_rotated=True,
    )
    analysis = analyze_ocr_result(result)

    assert calls == [b"original"]
    assert analysis["status"] == "success"
    assert analysis["materials"] == {"cotton": 100}


@pytest.mark.parametrize(
    "original",
    [
        ocr_text.OcrPayload("COTTON 80% POLYESTER 20%", "COTTON 20% POLYESTER 80%"),
        ocr_text.OcrPayload("COTTON 100%\nOLEFIN 50%", "COTTON 100%"),
        ocr_text.OcrPayload("COTTON 100%\nPOLYESTER -5%", "COTTON 100%"),
        ocr_text.OcrPayload(
            "OUTER COTTON 100%\nLINING POLYESTER 100%",
            "OUTER COTTON 80% NYLON 20%\nLINING POLYESTER 100%",
        ),
    ],
)
def test_irreversible_rejections_remain_failed_without_extra_calls(monkeypatch, original):
    result, calls = run_candidates(
        monkeypatch, {b"original": original},
        enable_reflection=True, enable_denoised=True, enable_rotated=True,
    )

    assert calls == [b"original"]
    assert analyze_ocr_result(result)["status"] == "failed"
    assert result.metadata.confidence == "low"


def test_recovery_does_not_start_after_total_deadline(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(ocr_text.time, "monotonic", lambda: clock["now"])

    def expired_response():
        clock["now"] = ocr_text.OCR_TOTAL_TIMEOUT_SECONDS
        return INCOMPLETE

    result, calls = run_candidates(monkeypatch, {b"original": expired_response})

    assert calls == [b"original"]
    assert result.metadata.attempts[-1].source == "preprocessed"
    assert result.metadata.attempts[-1].outcome == "skipped"
    assert result.metadata.attempts[-1].failure_code == "total_timeout"
    assert analyze_ocr_result(result)["status"] == "failed"


def test_recovery_failure_keeps_original_rejection(monkeypatch):
    result, calls = run_candidates(
        monkeypatch, {
            b"original": INCOMPLETE,
            b"basic": ocr_text.OcrTimeoutError("모의 OCR 시간 초과"),
        },
    )

    assert calls == [b"original", b"basic"]
    assert analyze_ocr_result(result)["status"] == "failed"
    assert result.metadata.attempts[-1].failure_code == "timeout"
    assert result.metadata.rejected_composition_parts


def test_offline_recovery_never_calls_vision_on_cache_miss(monkeypatch):
    cache = SimpleNamespace(get_entry=lambda content: (
        {"text": INCOMPLETE.text, "layout_text": INCOMPLETE.layout_text}
        if content == b"original" else None
    ))
    result, calls = run_candidates(monkeypatch, {}, ocr_cache=cache, offline=True)

    assert calls == []
    assert analyze_ocr_result(result)["status"] == "failed"
    assert result.metadata.external_call_count == 0
    assert any("OcrCacheMissError" in item for item in result.metadata.attempt_failures)
