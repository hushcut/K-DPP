"""AI 서비스의 HTTP 진입점.

텍스트 파싱과 라벨 OCR은 현재 DPP 통합 흐름에서 사용한다. 세탁기호
분류기는 별도 실험 기능이므로, 해당 API가 호출될 때만 의존성을 불러온다.
"""

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
from apps.service.response_contract import failed_label_response
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


def load_symbol_runtime():
    """세탁기호 API에서만 선택적 ResNet 의존성을 불러온다.

    OCR·소재 분석 서비스가 세탁기호 모델의 설치 상태에 영향을 받지 않게
    하는 경계다. 반환값을 묶어 테스트에서 예측 함수를 안전하게 대체할 수 있다.
    """

    from apps.symbol.model_io import ModelCheckpointError
    from apps.symbol.predict_symbol import (
        DEFAULT_MODEL_PATH,
        predict_symbol_bytes,
    )

    return ModelCheckpointError, DEFAULT_MODEL_PATH, predict_symbol_bytes


def failure_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    # 모든 실패 응답도 성공 응답과 같은 필드를 가져 프론트엔드 분기를 줄인다.
    return JSONResponse(
        status_code=status_code,
        content=failed_label_response(
            api_version=API_VERSION,
            error_code=error_code,
            message=message,
            extra=extra,
        ),
    )

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
        # 이 import는 현재 서비스의 핵심 OCR 경로와 의도적으로 분리돼 있다.
        model_checkpoint_error, default_model_path, predict_symbol = (
            load_symbol_runtime()
        )
        content = await read_upload(file)
        model_path = os.getenv(
            "KDPP_SYMBOL_MODEL_PATH",
            str(default_model_path),
        )
        result = predict_symbol(
            content,
            model_path=model_path,
        )
    except ModuleNotFoundError as exc:
        return failure_response(
            status_code=503,
            error_code="symbol_feature_unavailable",
            message=f"세탁기호 분류 의존성을 불러올 수 없습니다: {exc.name}",
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
    except model_checkpoint_error as exc:
        return failure_response(
            status_code=503,
            error_code="symbol_model_invalid",
            message=str(exc),
        )
    return JSONResponse(
        status_code=200,
        content={"api_version": API_VERSION, **result},
    )
