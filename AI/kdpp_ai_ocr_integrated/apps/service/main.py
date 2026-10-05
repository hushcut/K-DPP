"""AI 서비스의 HTTP 진입점.

Google Vision OCR, 소재·혼용률 분석과 텍스트 관리 지침 파싱을 제공한다.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.service.label_analysis import (
    API_VERSION,
    analyze_label_image_bytes,
    analyze_label_text,
)
from apps.service.response_contract import LabelResponseContract, failed_label_response
from apps.service.request_limits import BodySizeLimitMiddleware, MAX_REQUEST_BYTES
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
    description="Google Vision OCR과 소재 혼용률 파서의 AI 서비스 경계",
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES, api_version=API_VERSION)


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


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request, _exc: RequestValidationError):
    """Return the label schema even when FastAPI rejects the request body."""

    return failure_response(
        status_code=422,
        error_code="invalid_request",
        message="요청 형식이 올바르지 않습니다.",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request, exc: StarletteHTTPException):
    """Keep framework-generated HTTP errors in the public response contract."""

    return failure_response(
        status_code=exc.status_code,
        error_code="http_error",
        message="요청을 처리할 수 없습니다.",
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(_request, _exc: Exception):
    """Avoid leaking implementation details through an unhandled error body."""

    return failure_response(
        status_code=500,
        error_code="internal_error",
        message="AI 서비스 처리 중 내부 오류가 발생했습니다.",
    )


async def read_upload(file: UploadFile) -> bytes:
    try:
        content = await file.read(MAX_IMAGE_BYTES + 1)
    finally:
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


@app.post(
    "/v1/parse-text",
    response_model=LabelResponseContract,
    responses={
        400: {"model": LabelResponseContract, "description": "잘못된 요청 크기 헤더"},
        413: {"model": LabelResponseContract, "description": "전체 요청 본문 크기 초과"},
        422: {"model": LabelResponseContract, "description": "요청 또는 소재 조성 해석 실패"},
        500: {"model": LabelResponseContract, "description": "내부 처리 오류"},
    },
)
def parse_text(request: ParseTextRequest):
    """QA/debug endpoint for text already extracted by an OCR provider."""

    result = analyze_label_text(request.text)
    status_code = 200 if result["status"] == "success" else 422
    return JSONResponse(status_code=status_code, content=result)


@app.post(
    "/v1/analyze-label",
    response_model=LabelResponseContract,
    responses={
        400: {"model": LabelResponseContract, "description": "유효하지 않은 이미지"},
        413: {"model": LabelResponseContract, "description": "업로드 크기 초과"},
        415: {"model": LabelResponseContract, "description": "지원하지 않는 이미지 형식"},
        422: {"model": LabelResponseContract, "description": "요청 또는 소재 조성 해석 실패"},
        500: {"model": LabelResponseContract, "description": "내부 처리 오류"},
        502: {"model": LabelResponseContract, "description": "OCR 제공자 처리 실패"},
        503: {"model": LabelResponseContract, "description": "OCR 설정·사용량·가용성 오류"},
        504: {"model": LabelResponseContract, "description": "OCR 응답 시간 초과"},
    },
)
async def analyze_label(file: UploadFile = File(...)):
    try:
        declared_content_type = file.content_type
        content = await read_upload(file)
        result = await asyncio.to_thread(
            analyze_label_image_bytes,
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
    except OcrConfigurationError:
        return failure_response(
            status_code=503,
            error_code="ocr_not_configured",
            message="Google Vision OCR 설정을 확인해 주세요.",
        )
    except OcrQuotaExceededError:
        return failure_response(
            status_code=503,
            error_code="ocr_quota_exceeded",
            message="Google Vision OCR 사용량 한도를 초과했습니다.",
        )
    except OcrTimeoutError:
        return failure_response(
            status_code=504,
            error_code="ocr_timeout",
            message="Google Vision OCR 응답 시간이 초과되었습니다.",
        )
    except OcrUnavailableError:
        return failure_response(
            status_code=503,
            error_code="ocr_service_unavailable",
            message="Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다.",
        )
    except OcrServiceError:
        return failure_response(
            status_code=502,
            error_code="ocr_service_failed",
            message="Google Vision OCR 처리에 실패했습니다.",
        )

    status_code = 200 if result["status"] == "success" else 422
    return JSONResponse(status_code=status_code, content=result)
