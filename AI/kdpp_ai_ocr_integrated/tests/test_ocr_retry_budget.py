"""RPC retries must fit the candidate and request deadlines without real OCR."""

import datetime
import itertools
from types import SimpleNamespace

from google.api_core import exceptions, retry
from google.api_core.gapic_v1 import method
from google.api_core.timeout import TimeToDeadlineTimeout
import pytest

from apps.text import ocr_text
from apps.service.label_analysis import analyze_ocr_result
from apps.text.ocr_cache import OcrTextCache
from apps.text.ocr_regions import RegionImage
from scripts.ocr_failure_diagnostics import failure_diagnostics


@pytest.fixture
def clock(monkeypatch):
    state = {"now": 0.0}
    monkeypatch.setattr(ocr_text.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(
        ocr_text.time, "sleep", lambda seconds: state.update(now=state["now"] + seconds)
    )
    monkeypatch.setattr(retry, "exponential_sleep_generator", lambda **_kwargs: itertools.repeat(0.1))

    class ClockTimeout(TimeToDeadlineTimeout):
        def __init__(self, timeout):
            super().__init__(timeout, clock=lambda: datetime.datetime.fromtimestamp(
                state["now"], datetime.timezone.utc,
            ))

    monkeypatch.setattr(method, "TimeToDeadlineTimeout", ClockTimeout)
    return state


def response(text="COTTON 100%"):
    return SimpleNamespace(
        error=None,
        full_text_annotation=SimpleNamespace(text=text, pages=[]),
        text_annotations=[],
    )


def client_for(rpc):
    wrapped = method.wrap_method(rpc, default_retry=retry.Retry(), default_timeout=20)
    return SimpleNamespace(document_text_detection=wrapped)


def pipeline_environment(monkeypatch, client):
    monkeypatch.setattr(
        ocr_text, "validate_image_bytes",
        lambda *_args, **_kwargs: ocr_text.ValidatedImage(b"original", "PNG", 100, 100),
    )
    monkeypatch.setattr(ocr_text, "_resolve_credential_path", lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: client)
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: b"basic")
    monkeypatch.setattr(ocr_text, "preprocess_reflection_image_bytes", lambda _content: b"reflection")
    monkeypatch.setattr(ocr_text, "preprocess_denoised_image_bytes", lambda _content: b"denoised")
    monkeypatch.setattr(ocr_text, "preprocess_rotated_image_bytes", lambda _content: b"rotated")


def test_actual_rpc_retry_receives_only_remaining_candidate_time(clock):
    timeouts = []

    def rpc(*_args, **kwargs):
        timeouts.append(kwargs["timeout"])
        if len(timeouts) == 1:
            clock["now"] += 9.5
            raise exceptions.ServiceUnavailable("temporary")
        clock["now"] += kwargs["timeout"]
        return response()

    payload = ocr_text._run_google_ocr(client_for(rpc), b"image", timeout_seconds=10)
    assert timeouts == pytest.approx([10, 0.4])
    assert clock["now"] <= 10
    assert payload.retry_count == 1
    assert payload.rpc_attempt_count == 2


def test_insufficient_backoff_budget_does_not_start_or_count_a_retry(clock):
    calls = []

    def rpc(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        clock["now"] += 9.95
        raise exceptions.ServiceUnavailable("temporary")

    with pytest.raises(ocr_text.OcrUnavailableError) as caught:
        ocr_text._run_google_ocr(client_for(rpc), b"image", timeout_seconds=10)
    assert len(calls) == 1
    assert clock["now"] == 9.95
    assert caught.value.retry_count == 0
    assert caught.value.rpc_attempt_count == 1


@pytest.mark.parametrize("budget", [0, -1])
def test_empty_budget_starts_no_rpc(clock, budget):
    with pytest.raises(ocr_text.OcrTimeoutError) as caught:
        ocr_text._run_google_ocr(
            client_for(lambda **_kwargs: pytest.fail("no RPC budget")), b"image",
            timeout_seconds=budget,
        )
    assert caught.value.rpc_attempt_count == 0
    assert caught.value.retry_count == 0


def test_success_after_deadline_is_not_accepted(clock):
    def rpc(*_args, **kwargs):
        clock["now"] += kwargs["timeout"] + 0.5
        return response()

    with pytest.raises(ocr_text.OcrTimeoutError) as caught:
        ocr_text._run_google_ocr(client_for(rpc), b"image", timeout_seconds=10)
    assert caught.value.rpc_attempt_count == 1


def test_failed_retry_keeps_actual_rpc_count(clock):
    calls = []

    def rpc(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise exceptions.ServiceUnavailable("temporary")
        raise exceptions.ResourceExhausted("quota")

    with pytest.raises(ocr_text.OcrQuotaExceededError) as caught:
        ocr_text._run_google_ocr(client_for(rpc), b"image", timeout_seconds=10)
    assert len(calls) == caught.value.rpc_attempt_count == 2
    assert caught.value.retry_count == 1


def test_pipeline_rpc_retries_fit_25_seconds_and_have_separate_counts(monkeypatch, clock):
    timeouts = []

    def rpc(*_args, **kwargs):
        timeouts.append(kwargs["timeout"])
        if len(timeouts) % 2:
            clock["now"] += kwargs["timeout"] - 0.5
            raise exceptions.ServiceUnavailable("temporary")
        clock["now"] += kwargs["timeout"]
        return response("BRAND ONLY")

    pipeline_environment(monkeypatch, client_for(rpc))
    result = ocr_text.run_ocr_bytes(
        b"image", enable_reflection=True, enable_denoised=True, enable_rotated=True,
    )
    assert clock["now"] <= 25
    assert timeouts == pytest.approx([10, 0.4, 8, 0.4, 7, 0.4])
    assert result.metadata.external_call_count == 3
    assert result.metadata.rpc_attempt_count == 6
    assert result.metadata.retry_count == 3
    assert [a.rpc_attempt_count for a in result.metadata.attempts[:3]] == [2, 2, 2]
    assert all(a.outcome == "skipped" for a in result.metadata.attempts[3:])


def test_failed_additional_candidate_counts_retries(monkeypatch, clock):
    calls = []

    def rpc(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            return response("BRAND ONLY")
        if len(calls) == 2:
            raise exceptions.ServiceUnavailable("temporary")
        raise exceptions.ResourceExhausted("quota")

    pipeline_environment(monkeypatch, client_for(rpc))
    result = ocr_text.run_ocr_bytes(b"image", enable_reflection=False)
    assert result.metadata.external_call_count == 2
    assert result.metadata.rpc_attempt_count == 3
    assert result.metadata.retry_count == 1
    assert result.metadata.attempts[-1].rpc_attempt_count == 2
    assert result.metadata.attempts[-1].failure_code == "quota_exceeded"
    analysis = analyze_ocr_result(result)
    assert analysis["ocr"]["rpc_attempt_count"] == 3
    assert analysis["ocr"]["attempts"][-1]["rpc_attempt_count"] == 2


def test_client_setup_time_reduces_first_rpc_budget(monkeypatch, clock):
    timeouts = []
    client = client_for(lambda **kwargs: timeouts.append(kwargs["timeout"]) or response())
    pipeline_environment(monkeypatch, client)

    def slow_setup(*_args):
        clock["now"] += 3
        return client

    monkeypatch.setattr(ocr_text, "_get_vision_client", slow_setup)
    result = ocr_text.run_ocr_bytes(b"image")
    assert timeouts == pytest.approx([7])
    assert result.metadata.rpc_attempt_count == 1


def test_client_setup_exhausting_request_budget_starts_no_rpc(monkeypatch, clock):
    client = client_for(lambda **_kwargs: pytest.fail("setup exhausted RPC budget"))
    pipeline_environment(monkeypatch, client)

    def slow_setup(*_args):
        clock["now"] += 26
        return client

    monkeypatch.setattr(ocr_text, "_get_vision_client", slow_setup)
    with pytest.raises(ocr_text.OcrTotalTimeoutError):
        ocr_text.run_ocr_bytes(b"image")


@pytest.mark.parametrize("cached_text,status,materials", [
    ("BRAND ONLY", "failed", {}),
    ("COTTON\n80%\nPOLYESTER\n20%", "success", {"cotton": 80, "polyester": 20}),
])
def test_cached_original_setup_timeout_is_a_local_budget_event(
    monkeypatch, clock, cached_text, status, materials,
):
    client = client_for(lambda **_kwargs: pytest.fail("local budget must prevent RPC"))
    pipeline_environment(monkeypatch, client)
    cache = SimpleNamespace(get_entry=lambda content: (
        {"text": cached_text} if content == b"original" else None
    ))

    def slow_setup(*_args):
        clock["now"] += ocr_text.OCR_TOTAL_TIMEOUT_SECONDS + 1
        return client

    monkeypatch.setattr(ocr_text, "_get_vision_client", slow_setup)
    result = ocr_text.run_ocr_bytes(
        b"image", ocr_cache=cache, enable_reflection=False,
        enable_denoised=False, enable_rotated=False, enable_material_region=False,
    )
    attempt = result.metadata.attempts[-1]
    assert attempt.source == "preprocessed" and attempt.outcome == "failed"
    assert attempt.failure_code == "total_timeout"
    assert attempt.external_call is False
    assert result.metadata.external_call_count == result.metadata.rpc_attempt_count == 0
    assert attempt.rpc_attempt_count == attempt.retry_count == result.metadata.retry_count == 0
    analysis = analyze_ocr_result(result)
    assert analysis["status"] == status and analysis["materials"] == materials
    diagnostic = failure_diagnostics(analysis)
    assert diagnostic["budget_exhausted"] is True
    assert diagnostic["service_error_codes"] == []
    assert diagnostic["failure_stage"] == ("success" if status == "success" else "composition")


def test_offline_cache_hit_has_zero_rpc_attempts(monkeypatch, clock, tmp_path):
    client = client_for(lambda **_kwargs: pytest.fail("offline must not call RPC"))
    pipeline_environment(monkeypatch, client)
    cache = OcrTextCache(tmp_path / "cache.json")
    cache.put(b"original", "COTTON 100%")
    result = ocr_text.run_ocr_bytes(b"image", ocr_cache=cache, offline=True)
    assert result.metadata.rpc_attempt_count == 0
    assert result.metadata.external_call_count == 0
    assert result.metadata.retry_count == 0


def test_backoff_oversleep_does_not_start_another_rpc(monkeypatch, clock):
    calls = []

    def rpc(*_args, **kwargs):
        calls.append(kwargs["timeout"])
        clock["now"] += 9.5
        raise exceptions.ServiceUnavailable("temporary")

    monkeypatch.setattr(
        ocr_text.time, "sleep", lambda _seconds: clock.update(now=clock["now"] + 1)
    )
    with pytest.raises(ocr_text.OcrTimeoutError) as caught:
        ocr_text._run_google_ocr(client_for(rpc), b"image", timeout_seconds=10)
    assert len(calls) == caught.value.rpc_attempt_count == 1
    assert caught.value.retry_count == 0


def test_provider_payload_setup_exhausting_budget_is_not_counted_as_rpc(monkeypatch, clock):
    from google.cloud import vision

    calls = []
    image_type = vision.Image

    def slow_image(**kwargs):
        if kwargs["content"] == b"basic":
            clock["now"] += 9
        return image_type(**kwargs)

    monkeypatch.setattr(vision, "Image", slow_image)
    pipeline_environment(monkeypatch, client_for(
        lambda **kwargs: calls.append(kwargs["timeout"]) or response("BRAND ONLY")
    ))
    result = ocr_text.run_ocr_bytes(b"image", enable_reflection=False)
    assert len(calls) == result.metadata.rpc_attempt_count == 1
    assert result.metadata.external_call_count == 1
    assert result.metadata.attempts[-1].rpc_attempt_count == 0
    assert result.metadata.attempts[-1].external_call is False


@pytest.mark.parametrize("path", [
    "preprocessed", "reflection", "denoised", "rotated",
    "material_crop", "material_crop_rotated", "early_crop",
])
@pytest.mark.parametrize("failure", ["invalid_image", "memory", "service", "prepare_timeout"])
def test_optional_candidate_failure_keeps_counts_and_budget_distinct(monkeypatch, clock, path, failure):
    """모든 추가 입력에서 준비 실패·호출 실패·전체 예산 소진을 구별한다."""
    target = "material_crop_rotated" if path == "early_crop" else path
    calls = []
    preparations = []
    pipeline_environment(monkeypatch, None)

    def prepare(source):
        preparations.append(source)
        if source == target:
            if failure == "invalid_image":
                raise ocr_text.InvalidImageError("private detail")
            if failure == "memory":
                raise MemoryError("private detail")
            if failure == "prepare_timeout":
                clock["now"] = ocr_text.OCR_TOTAL_TIMEOUT_SECONDS + 1
        return source.encode()

    def ocr(_client, content, **_kwargs):
        source = content.decode()
        calls.append(source)
        if source == target and failure == "service":
            raise ocr_text.OcrUnavailableError("private detail", rpc_attempt_count=1)
        return ocr_text.OcrPayload("BRAND ONLY", rpc_attempt_count=1)

    monkeypatch.setattr(ocr_text, "_run_google_ocr", ocr)
    for source, name in [
        ("preprocessed", "preprocess_image_bytes"),
        ("reflection", "preprocess_reflection_image_bytes"),
        ("denoised", "preprocess_denoised_image_bytes"),
        ("rotated", "preprocess_rotated_image_bytes"),
    ]:
        monkeypatch.setattr(ocr_text, name, lambda _content, source=source: prepare(source))

    cropped = path.startswith("material_crop") or path == "early_crop"
    region = (0.0, 0.0, 100.0, 100.0)
    monkeypatch.setattr(ocr_text, "find_material_region", lambda *_args: region)
    monkeypatch.setattr(ocr_text, "find_complete_material_region",
                        lambda *_args: region if path == "early_crop" else None)
    monkeypatch.setattr(ocr_text, "material_region_options", lambda *_args: (10.0, 0.0))
    monkeypatch.setattr(ocr_text, "material_region_word_boxes", lambda *_args: ())
    monkeypatch.setattr(ocr_text, "color_material_region_angle", lambda *_args: None)

    def prepare_crop(_content, _region, *, rotated, **_kwargs):
        source = "material_crop_rotated" if rotated else "material_crop"
        return RegionImage(prepare(source), source, (1, 0, 0, 0, 1, 0), region)

    monkeypatch.setattr(ocr_text, "prepare_material_region", prepare_crop)
    result = ocr_text.run_ocr_bytes(
        b"image", enable_reflection=path == "reflection",
        enable_denoised=path == "denoised", enable_rotated=path == "rotated",
        enable_material_region=cropped,
    )
    attempts = result.metadata.attempts
    assert target in preparations
    assert result.metadata.candidate_count == sum(a.outcome == "success" for a in attempts)
    assert len(calls) == result.metadata.external_call_count == result.metadata.rpc_attempt_count
    assert calls[0] == "original"
    assert "private detail" not in repr(result.metadata)
    if failure == "prepare_timeout":
        assert target not in calls
        assert f"{target}:total_timeout" in result.metadata.attempt_failures
        target_attempt = next(a for a in attempts if a.source == target)
        assert target_attempt.outcome == "skipped"
        assert target_attempt.failure_code == "total_timeout"
        assert not target_attempt.external_call and target_attempt.rpc_attempt_count == 0
        assert all(a.outcome == "skipped" for a in attempts[attempts.index(target_attempt):])
    elif failure == "service":
        target_attempt = next(a for a in attempts if a.source == target)
        assert target_attempt.outcome == "failed"
        assert target_attempt.failure_code == "service_unavailable"
        assert target_attempt.external_call and target_attempt.rpc_attempt_count == 1
    else:
        assert target not in calls
        assert not any(a.source == target for a in attempts)
        error_name = "InvalidImageError" if failure == "invalid_image" else "MemoryError"
        assert f"{target}:{error_name}" in result.metadata.attempt_failures
