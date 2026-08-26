from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from apps.service.label_analysis import (
    API_VERSION,
    analyze_label_image_bytes,
    analyze_label_text,
)
from apps.symbol.model_io import ModelCheckpointError
from apps.symbol.predict_symbol import (
    DEFAULT_MODEL_PATH,
    predict_symbol_bytes,
)
from apps.text.ocr_text import (
    ImageTooLargeError,
    InvalidImageError,
    MAX_IMAGE_BYTES,
    OcrConfigurationError,
    OcrQuotaExceededError,
    OcrServiceError,
    OcrTimeoutError,
    OcrUnavailableError,
    UnsupportedImageError,
)


app = FastAPI(
    title="K-DPP AI Label Service",
    version=API_VERSION,
    description=(
        "Google Vision OCR, 소재 혼용률 파서, 세탁기호 crop 분류기의 "
        "단일 AI 서비스 경계"
    ),
)


class ParseTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50_000)


def failure_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "api_version": API_VERSION,
        "status": "failed",
        "error_code": error_code,
        "message": message,
        "materials": {},
        "materials_korean": "",
        "raw_ocr_preview": "",
    }
    if extra:
        content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_IMAGE_BYTES + 1)
    await file.close()
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(
            f"이미지 파일은 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 이하여야 합니다."
        )
    return content


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "kdpp-ai-label",
        "api_version": API_VERSION,
    }


@app.post("/v1/parse-text")
def parse_text(request: ParseTextRequest):
    """QA/debug endpoint for text already extracted by an OCR provider."""

    result = analyze_label_text(request.text)
    status_code = 200 if result["status"] == "success" else 422
    return JSONResponse(status_code=status_code, content=result)


@app.post("/v1/analyze-label")
async def analyze_label(file: UploadFile = File(...)):
    try:
        declared_content_type = file.content_type
        content = await read_upload(file)
        result = analyze_label_image_bytes(
            content,
            declared_content_type=declared_content_type,
        )
    except ImageTooLargeError as exc:
        return failure_response(
            status_code=413,
            error_code="payload_too_large",
            message=str(exc),
        )
    except UnsupportedImageError as exc:
        return failure_response(
            status_code=415,
            error_code="unsupported_media_type",
            message=str(exc),
        )
    except InvalidImageError as exc:
        return failure_response(
            status_code=400,
            error_code="invalid_image",
            message=str(exc),
        )
    except OcrConfigurationError as exc:
        return failure_response(
            status_code=503,
            error_code="ocr_not_configured",
            message=str(exc),
        )
    except OcrQuotaExceededError as exc:
        return failure_response(
            status_code=503,
            error_code="ocr_quota_exceeded",
            message=str(exc),
        )
    except OcrTimeoutError as exc:
        return failure_response(
            status_code=504,
            error_code="ocr_timeout",
            message=str(exc),
        )
    except OcrUnavailableError as exc:
        return failure_response(
            status_code=503,
            error_code="ocr_service_unavailable",
            message=str(exc),
        )
    except OcrServiceError as exc:
        return failure_response(
            status_code=502,
            error_code="ocr_service_failed",
            message=str(exc),
        )

    status_code = 200 if result["status"] == "success" else 422
    return JSONResponse(status_code=status_code, content=result)


@app.post("/v1/analyze-symbol")
async def analyze_symbol(file: UploadFile = File(...)):
    """Classify an already-cropped care symbol, not a full care-label photo."""

    try:
        content = await read_upload(file)
        model_path = os.getenv(
            "KDPP_SYMBOL_MODEL_PATH",
            str(DEFAULT_MODEL_PATH),
        )
        result = predict_symbol_bytes(
            content,
            model_path=model_path,
        )
    except ImageTooLargeError as exc:
        return failure_response(
            status_code=413,
            error_code="payload_too_large",
            message=str(exc),
        )
    except ValueError as exc:
        return failure_response(
            status_code=400,
            error_code="invalid_image",
            message=str(exc),
        )
    except FileNotFoundError as exc:
        return failure_response(
            status_code=503,
            error_code="symbol_model_not_configured",
            message=str(exc),
        )
    except ModelCheckpointError as exc:
        return failure_response(
            status_code=503,
            error_code="symbol_model_invalid",
            message=str(exc),
        )
    return JSONResponse(
        status_code=200,
        content={"api_version": API_VERSION, **result},
    )
