from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.service import main as service_main
from apps.symbol.model_io import ModelCheckpointError
from apps.text.ocr_text import (
    OcrConfigurationError,
    OcrQuotaExceededError,
    OcrServiceError,
    OcrTimeoutError,
    OcrUnavailableError,
)


client = TestClient(service_main.app)


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (80, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


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


def test_analyze_label_maps_ocr_provider_failure_to_502(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise OcrServiceError("provider unavailable")

    monkeypatch.setattr(service_main, "analyze_label_image_bytes", fail)
    response = client.post(
        "/v1/analyze-label",
        files={"file": ("label.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 502
    assert response.json()["error_code"] == "ocr_service_failed"


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


def test_analyze_symbol_returns_versioned_success_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        service_main,
        "predict_symbol_bytes",
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
    )

    response = client.post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["api_version"] == service_main.API_VERSION
    assert response.json()["model_scope"] == "cropped_care_symbol_only"


def test_analyze_symbol_maps_invalid_checkpoint_to_503(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise ModelCheckpointError("checkpoint architecture mismatch")

    monkeypatch.setattr(service_main, "predict_symbol_bytes", fail)
    response = client.post(
        "/v1/analyze-symbol",
        files={"file": ("symbol.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "symbol_model_invalid"
