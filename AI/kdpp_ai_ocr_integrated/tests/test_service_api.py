import asyncio
import threading
from io import BytesIO

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from apps.service import main as service_main
from apps.service.label_analysis import analyze_ocr_result
from apps.service.response_contract import LABEL_RESPONSE_DEFAULTS
from apps.text.ocr_text import (
    OcrAttempt,
    OcrConfigurationError,
    OcrMetadata,
    OcrQuotaExceededError,
    OcrResult,
    OcrServiceError,
    OcrTimeoutError,
    OcrUnavailableError,
)


client = TestClient(service_main.app)


def symbol_client() -> TestClient:
    application = FastAPI()
    service_main.register_symbol_api(application, enabled=True)
    return TestClient(application)


def test_symbol_api_registration_is_opt_in() -> None:
    text_only_app = FastAPI()
    symbol_app = FastAPI()

    assert service_main.register_symbol_api(text_only_app, enabled=False) is False
    assert "/v1/analyze-symbol" not in text_only_app.openapi()["paths"]

    assert service_main.register_symbol_api(symbol_app, enabled=True) is True
    assert "/v1/analyze-symbol" in symbol_app.openapi()["paths"]


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_symbol_api_accepts_explicit_enable_values(value) -> None:
    assert service_main.symbol_api_enabled(value) is True


@pytest.mark.parametrize("value", ["", "0", "false", "off", "unexpected"])
def test_symbol_api_rejects_other_values(value) -> None:
    assert service_main.symbol_api_enabled(value) is False


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (80, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def run_with_event_loop_probe(request, started: threading.Event, release: threading.Event):
    async def run():
        async def release_when_started():
            assert await asyncio.to_thread(started.wait, 0.4)
            release.set()

        response, _ = await asyncio.wait_for(
            asyncio.gather(request(), release_when_started()),
            timeout=0.4,
        )
        return response

    return asyncio.run(run())


def assert_failure_contract(response, *, status_code: int, error_code: str) -> None:
    assert response.status_code == status_code
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == error_code
    assert payload["api_version"] == service_main.API_VERSION
    assert set(LABEL_RESPONSE_DEFAULTS).issubset(payload)


def test_read_upload_closes_file_when_read_fails() -> None:
    class FailingUpload:
        closed = False

        async def read(self, _size: int) -> bytes:
            raise RuntimeError("read failed")

        async def close(self) -> None:
            self.closed = True

    upload = FailingUpload()
    with pytest.raises(RuntimeError, match="read failed"):
        asyncio.run(service_main.read_upload(upload))

    assert upload.closed is True


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "kdpp-ai-label"


def test_parse_text_success_and_failure_contract() -> None:
    success = client.post(
        "/v1/parse-text",
        json={"text": "COTTON 80% POLYESTER 20%"},
    )
    failure = client.post(
        "/v1/parse-text",
        json={"text": "BRAND SIZE 100"},
    )

    assert success.status_code == 200
    assert success.json()["materials"] == {"cotton": 80, "polyester": 20}
    assert failure.status_code == 422
    assert failure.json()["status"] == "failed"
    assert failure.json()["error_code"] == "composition_not_found"


@pytest.mark.parametrize(
    ("path", "request_kwargs"),
    [
        ("/v1/parse-text", {"json": {"text": ""}}),
        (
            "/v1/parse-text",
            {
                "content": b'{"text":',
                "headers": {"content-type": "application/json"},
            },
        ),
        ("/v1/analyze-label", {}),
    ],
)
def test_request_validation_errors_use_failure_contract(path, request_kwargs) -> None:
    response = client.post(path, **request_kwargs)

    assert_failure_contract(
        response,
        status_code=422,
        error_code="invalid_request",
    )


def test_http_error_uses_failure_contract() -> None:
    response = client.get("/v1/not-found")

    assert_failure_contract(
        response,
        status_code=404,
        error_code="http_error",
    )


def test_unexpected_service_error_uses_failure_contract(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("unexpected implementation detail")

    monkeypatch.setattr(service_main, "analyze_label_image_bytes", fail)
    isolated_client = TestClient(service_main.app, raise_server_exceptions=False)
    response = isolated_client.post(
        "/v1/analyze-label",
        files={"file": ("label.png", image_bytes(), "image/png")},
    )

    assert_failure_contract(
        response,
        status_code=500,
        error_code="internal_error",
    )
    assert "unexpected implementation detail" not in response.text


def test_analyze_label_returns_consistent_success_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        service_main,
        "analyze_label_image_bytes",
        lambda *_args, **_kwargs: {
            "api_version": "1.0",
            "status": "success",
            "materials": {"cotton": 100},
            "materials_korean": "면 100%",
            "raw_ocr_preview": "COTTON 100%",
            "confidence": {"ocr": "high", "parser": "high"},
        },
    )

    response = client.post(
        "/v1/analyze-label",
        files={"file": ("label.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["materials"] == {"cotton": 100}


def test_analyze_label_keeps_event_loop_responsive_during_ocr(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    async def read_upload_stub(_file):
        return image_bytes()

    def waiting_ocr(*_args, **_kwargs):
        started.set()
        release.wait(0.8)
        return {"status": "success"}

    monkeypatch.setattr(service_main, "read_upload", read_upload_stub)
    monkeypatch.setattr(service_main, "analyze_label_image_bytes", waiting_ocr)
    response = run_with_event_loop_probe(
        lambda: service_main.analyze_label(
            UploadFile(filename="label.png", file=BytesIO(b"image"))
        ),
        started,
        release,
    )

    assert response.status_code == 200


def test_ocr_attempt_diagnostics_are_safe_and_serialized() -> None:
    result = analyze_ocr_result(
        OcrResult(
            text="COTTON 100%",
            metadata=OcrMetadata(
                source="original",
                confidence="high",
                candidate_count=2,
                image_format="JPEG",
                width=1200,
                height=800,
                attempt_failures=("reflection:OcrTimeoutError",),
                attempt_count=3,
                external_call_count=3,
                retry_count=1,
                elapsed_ms=321,
                attempts=(
                    OcrAttempt(
                        source="reflection",
                        outcome="failed",
                        elapsed_ms=200,
                        external_call=True,
                        failure_code="timeout",
                        retry_count=1,
                    ),
                ),
            ),
        )
    )

    assert result["ocr"] == {
        "source": "original",
        "candidate_count": 2,
        "image_format": "JPEG",
        "width": 1200,
        "height": 800,
        "attempt_failures": ["reflection:OcrTimeoutError"],
        "attempt_count": 3,
        "external_call_count": 3,
        "retry_count": 1,
        "elapsed_ms": 321,
        "attempts": [
            {
                "source": "reflection",
                "outcome": "failed",
                "elapsed_ms": 200,
                "external_call": True,
                "failure_code": "timeout",
                "retry_count": 1,
            }
        ],
    }


def test_analyze_label_maps_ocr_provider_failure_to_502(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise OcrServiceError("provider unavailable: C:/credentials/private-key.json")

    monkeypatch.setattr(service_main, "analyze_label_image_bytes", fail)
    response = client.post(
        "/v1/analyze-label",
        files={"file": ("label.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 502
    assert response.json()["error_code"] == "ocr_service_failed"
    assert "private-key.json" not in response.text


@pytest.mark.parametrize(
    ("error", "status_code", "error_code"),
    [
        (OcrConfigurationError("configuration"), 503, "ocr_not_configured"),
        (
            OcrQuotaExceededError("quota exceeded"),
            503,
            "ocr_quota_exceeded",
        ),
        (OcrTimeoutError("timeout"), 504, "ocr_timeout"),
        (
            OcrUnavailableError("unavailable"),
            503,
            "ocr_service_unavailable",
        ),
    ],
)
def test_analyze_label_maps_specific_ocr_failures(
    monkeypatch,
    error,
    status_code,
    error_code,
) -> None:
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(service_main, "analyze_label_image_bytes", fail)
    response = client.post(
        "/v1/analyze-label",
        files={"file": ("label.png", image_bytes(), "image/png")},
    )

    assert response.status_code == status_code
    assert response.json()["error_code"] == error_code
    assert str(error) not in response.json()["message"]


def test_analyze_symbol_returns_versioned_success_contract(monkeypatch) -> None:
    class InvalidCheckpointError(Exception):
        pass

    monkeypatch.setattr(
        service_main,
        "load_symbol_runtime",
        lambda: (
            InvalidCheckpointError,
            "models/symbol.pt",
            lambda *_args, **_kwargs: {
                "symbols": [
                    {
                        "class": "wash_30",
                        "label_ko": "30도 세탁",
                        "confidence": 0.91,
                    }
                ],
                "model_scope": "cropped_care_symbol_only",
            },
        ),
    )

    response = symbol_client().post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["api_version"] == service_main.API_VERSION
    assert response.json()["model_scope"] == "cropped_care_symbol_only"


@pytest.mark.parametrize("blocked_stage", ["runtime", "prediction"])
def test_analyze_symbol_keeps_event_loop_responsive(monkeypatch, blocked_stage) -> None:
    class InvalidCheckpointError(Exception):
        pass

    started = threading.Event()
    release = threading.Event()

    async def read_upload_stub(_file):
        return image_bytes()

    def wait_if_selected(stage):
        if blocked_stage == stage:
            started.set()
            release.wait(0.8)

    def load_runtime_stub():
        wait_if_selected("runtime")

        def predict_stub(*_args, **_kwargs):
            wait_if_selected("prediction")
            return {"status": "success", "symbols": []}

        return InvalidCheckpointError, "models/symbol.pt", predict_stub

    monkeypatch.setattr(service_main, "read_upload", read_upload_stub)
    monkeypatch.setattr(service_main, "load_symbol_runtime", load_runtime_stub)
    response = run_with_event_loop_probe(
        lambda: service_main.analyze_symbol(
            UploadFile(filename="symbol.png", file=BytesIO(b"image"))
        ),
        started,
        release,
    )

    assert response.status_code == 200


def test_analyze_symbol_maps_invalid_checkpoint_to_503(monkeypatch) -> None:
    class InvalidCheckpointError(Exception):
        pass

    def fail(*_args, **_kwargs):
        raise InvalidCheckpointError("checkpoint architecture mismatch")

    monkeypatch.setattr(
        service_main,
        "load_symbol_runtime",
        lambda: (InvalidCheckpointError, "models/symbol.pt", fail),
    )
    response = symbol_client().post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "symbol_model_invalid"
    assert "architecture mismatch" not in response.text


def test_analyze_symbol_hides_missing_model_path(monkeypatch) -> None:
    class InvalidCheckpointError(Exception):
        pass

    def fail(*_args, **_kwargs):
        raise FileNotFoundError("C:/models/private/symbol.pt")

    monkeypatch.setattr(
        service_main,
        "load_symbol_runtime",
        lambda: (InvalidCheckpointError, "models/symbol.pt", fail),
    )
    response = symbol_client().post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "symbol_model_not_configured"
    assert "C:/models/private" not in response.text


def test_analyze_symbol_isolated_when_optional_runtime_is_missing(monkeypatch) -> None:
    def unavailable_runtime():
        raise ModuleNotFoundError("No module named 'torchvision'", name="torchvision")

    monkeypatch.setattr(service_main, "load_symbol_runtime", unavailable_runtime)
    response = symbol_client().post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "symbol_feature_unavailable"
    assert "torchvision" not in response.text
