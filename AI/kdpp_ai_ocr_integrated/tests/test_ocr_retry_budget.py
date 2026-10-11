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
