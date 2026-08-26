from __future__ import annotations

import math
import os
import re
import warnings
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from apps.text.ocr_cache import OcrCacheMissError, OcrTextCache

LANGUAGE_HINTS = ["ko", "en", "ja", "zh-Hans", "zh-Hant"]
MIN_OCR_WIDTH = 1800
MAX_OCR_WIDTH = 3200
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_ASPECT_RATIO = 20.0
MAX_PREPROCESSED_PIXELS = 16_000_000
MAX_PREPROCESSED_DIMENSION = 8192
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG"}
OCR_TIMEOUT_SECONDS = 20

# Keep Pillow's own decompression-bomb protection aligned with the API limit.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class OcrError(RuntimeError):
    """Base exception for errors raised by the OCR boundary."""


class InvalidImageError(OcrError):
    """The uploaded bytes do not contain a supported, safe image."""


class ImageTooLargeError(InvalidImageError):
    """The uploaded image exceeds the byte or pixel limit."""


class UnsupportedImageError(InvalidImageError):
    """The uploaded image format is not supported."""


class OcrConfigurationError(OcrError):
    """Google Vision credentials are missing or invalid."""


class OcrServiceError(OcrError):
    """Google Vision could not complete the OCR request."""


class OcrQuotaExceededError(OcrServiceError):
    """Google Vision rejected the request because its quota was exhausted."""


class OcrTimeoutError(OcrServiceError):
    """Google Vision did not complete the request before the deadline."""


class OcrUnavailableError(OcrServiceError):
    """Google Vision is temporarily unavailable after retries."""


@dataclass(frozen=True)
class OcrMetadata:
    source: str
    confidence: str
    candidate_count: int
    image_format: str
    width: int
    height: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class OcrResult:
    text: str
    metadata: OcrMetadata


@dataclass(frozen=True)
class OcrCandidate:
    source: str
    text: str
    materials: dict[str, float | int]
    parser_status: str
    parser_confidence: str
    score: tuple[int, int, float, int, int, int]


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    image_format: str
    width: int
    height: int


def _validate_image_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise InvalidImageError("이미지 크기가 올바르지 않습니다.")

    if width * height >= MAX_IMAGE_PIXELS:
        raise ImageTooLargeError("이미지 해상도가 너무 큽니다.")

    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > MAX_IMAGE_ASPECT_RATIO:
        raise ImageTooLargeError("이미지의 가로세로 비율이 너무 큽니다.")


def read_image_bytes(image_path: str | os.PathLike[str]) -> bytes:
    try:
        return Path(image_path).read_bytes()
    except OSError as exc:
        raise InvalidImageError(f"이미지 파일을 읽을 수 없습니다: {image_path}") from exc


def validate_image_bytes(
    content: bytes,
    *,
    declared_content_type: str | None = None,
) -> ValidatedImage:
    if not content:
        raise InvalidImageError("이미지 파일이 비어 있습니다.")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError(
            f"이미지 파일은 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 이하여야 합니다."
        )

    if declared_content_type:
        normalized_type = declared_content_type.split(";", 1)[0].strip().lower()
        if normalized_type not in {"image/jpeg", "image/png"}:
            raise UnsupportedImageError("JPG 또는 PNG 이미지만 지원합니다.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
                _validate_image_dimensions(width, height)
                image.verify()
    except InvalidImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "안전한 처리 범위를 넘는 고해상도 이미지입니다."
        ) from exc
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidImageError("올바른 이미지 파일이 아닙니다.") from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "이미지가 너무 커서 안전하게 처리할 수 없습니다."
        ) from exc

    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise UnsupportedImageError("JPG 또는 PNG 이미지만 지원합니다.")

    return ValidatedImage(
        content=content,
        image_format=image_format,
        width=width,
        height=height,
    )


def preprocess_image_bytes(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            _validate_image_dimensions(width, height)

            scale = 1.0
            if width < MIN_OCR_WIDTH:
                scale = MIN_OCR_WIDTH / width
            elif width > MAX_OCR_WIDTH:
                scale = MAX_OCR_WIDTH / width

            pixel_scale = math.sqrt(
                MAX_PREPROCESSED_PIXELS / (width * height)
            )
            dimension_scale = MAX_PREPROCESSED_DIMENSION / max(width, height)
            scale = min(scale, pixel_scale, dimension_scale)

            if scale != 1.0:
                resampling = getattr(Image, "Resampling", Image)
                output_width = max(1, int(width * scale))
                output_height = max(1, int(height * scale))
                image = image.resize(
                    (output_width, output_height),
                    resampling.LANCZOS,
                )

            image = ImageOps.autocontrast(image.convert("L"))
            image = image.filter(
                ImageFilter.UnsharpMask(radius=1.4, percent=150, threshold=3)
            )

            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            "OCR 전처리 범위를 넘는 고해상도 이미지입니다."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("OCR 전처리 중 이미지 디코딩에 실패했습니다.") from exc
    except MemoryError as exc:
        raise ImageTooLargeError(
            "OCR 전처리 중 이미지가 너무 커서 메모리가 부족합니다."
        ) from exc


def _parse_candidate(text: str) -> dict:
    from apps.text.parse_label import parse_label

    return parse_label(text)


def _score_candidate(
    text: str,
    materials: dict[str, float | int],
    parser_status: str,
    parser_confidence: str,
    source: str,
    *,
    ratio_total_before_normalization: float | None,
    warning_count: int,
) -> tuple[int, int, float, int, int, int]:
    total = (
        ratio_total_before_normalization
        if ratio_total_before_normalization is not None
        else sum(float(value) for value in materials.values())
        if materials
        else 0.0
    )
    confidence_rank = {"low": 0, "medium": 1, "high": 2}.get(parser_confidence, 0)
    explicit_percent_count = len(re.findall(r"\d{1,3}(?:\.\d+)?\s*[%％]", text))
    source_priority = 1 if source == "original" else 0

    return (
        1 if parser_status == "success" else 0,
        confidence_rank,
        -abs(100.0 - total) if materials else -100.0,
        -warning_count,
        min(explicit_percent_count, 4),
        source_priority,
    )


def _build_candidate(source: str, text: str) -> OcrCandidate:
    parsed = _parse_candidate(text)
    materials = parsed.get("materials", {})
    parser_status = parsed.get("status", "failed")
    parser_confidence = parsed.get("confidence", {}).get("parser", "low")
    ratio_total = parsed.get("parse_evidence", {}).get(
        "ratio_total_before_normalization"
    )
    parser_warnings = parsed.get("warnings", [])
    return OcrCandidate(
        source=source,
        text=text,
        materials=materials,
        parser_status=parser_status,
        parser_confidence=parser_confidence,
        score=_score_candidate(
            text,
            materials,
            parser_status,
            parser_confidence,
            source,
            ratio_total_before_normalization=ratio_total,
            warning_count=len(parser_warnings),
        ),
    )


def _extract_response_text(response: Any) -> str:
    error = getattr(response, "error", None)
    error_message = getattr(error, "message", "")
    if error_message:
        error_code = getattr(error, "code", None)
        if error_code in {7, 16}:  # PERMISSION_DENIED, UNAUTHENTICATED
            raise OcrConfigurationError(
                "Google Vision 인증 권한 또는 결제 설정을 확인해 주세요."
            )
        if error_code == 8:  # RESOURCE_EXHAUSTED
            raise OcrQuotaExceededError(
                "Google Vision OCR 사용량 한도를 초과했습니다."
            )
        if error_code == 4:  # DEADLINE_EXCEEDED
            raise OcrTimeoutError("Google Vision OCR 요청 시간이 초과되었습니다.")
        if error_code in {13, 14}:  # INTERNAL, UNAVAILABLE
            raise OcrUnavailableError(
                "Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다."
            )
        raise OcrServiceError(error_message)

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text

    texts = response.text_annotations
    return texts[0].description if texts else ""


def _resolve_credential_path(
    credential_path: str | None,
) -> tuple[str | None, int | None]:
    value = credential_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not value:
        return None, None

    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise OcrConfigurationError(f"Google Vision 서비스 계정 키를 찾을 수 없습니다: {path}")
    return str(path), path.stat().st_mtime_ns


@lru_cache(maxsize=4)
def _get_vision_client(
    resolved_credential_path: str | None,
    credential_modified_time_ns: int | None,
):
    del credential_modified_time_ns
    try:
        from google.cloud import vision
        from google.oauth2 import service_account
    except ImportError as exc:
        raise OcrConfigurationError(
            "google-cloud-vision 패키지가 설치되어 있지 않습니다."
        ) from exc

    try:
        if resolved_credential_path:
            credentials = service_account.Credentials.from_service_account_file(
                resolved_credential_path
            )
            return vision.ImageAnnotatorClient(credentials=credentials)
        return vision.ImageAnnotatorClient()
    except Exception as exc:
        raise OcrConfigurationError("Google Vision 인증 정보를 불러오지 못했습니다.") from exc


def _run_google_ocr(client: Any, content: bytes) -> str:
    from google.api_core import exceptions as google_exceptions
    from google.api_core import retry as google_retry
    from google.cloud import vision

    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=LANGUAGE_HINTS)
    retry = google_retry.Retry(
        predicate=google_retry.if_exception_type(
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError,
        ),
        initial=0.5,
        maximum=2.0,
        multiplier=2.0,
        deadline=OCR_TIMEOUT_SECONDS,
    )

    try:
        response = client.document_text_detection(
            image=image,
            image_context=image_context,
            retry=retry,
            timeout=OCR_TIMEOUT_SECONDS,
        )
        return _extract_response_text(response).strip()
    except OcrServiceError:
        raise
    except OcrConfigurationError:
        raise
    except (google_exceptions.GoogleAPIError, TimeoutError) as exc:
        cause = getattr(exc, "cause", None) or exc
        if isinstance(
            cause,
            (google_exceptions.Unauthorized, google_exceptions.Forbidden),
        ):
            raise OcrConfigurationError(
                "Google Vision 인증 권한 또는 결제 설정을 확인해 주세요."
            ) from exc
        if isinstance(cause, google_exceptions.TooManyRequests):
            raise OcrQuotaExceededError(
                "Google Vision OCR 사용량 한도를 초과했습니다."
            ) from exc
        if isinstance(cause, (google_exceptions.DeadlineExceeded, TimeoutError)):
            raise OcrTimeoutError(
                "Google Vision OCR 요청 시간이 초과되었습니다."
            ) from exc
        if isinstance(
            cause,
            (
                google_exceptions.ServiceUnavailable,
                google_exceptions.InternalServerError,
            ),
        ):
            raise OcrUnavailableError(
                "Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다."
            ) from exc
        raise OcrServiceError("Google Vision OCR 요청에 실패했습니다.") from exc


def run_ocr_bytes(
    content: bytes,
    credential_path: str | None = None,
    *,
    declared_content_type: str | None = None,
    ocr_cache: OcrTextCache | None = None,
    refresh_ocr_cache: bool = False,
    offline: bool = False,
    cache_label: str = "",
) -> OcrResult:
    validated = validate_image_bytes(
        content,
        declared_content_type=declared_content_type,
    )
    if offline and ocr_cache is None:
        raise OcrCacheMissError("오프라인 OCR 실행에는 캐시 파일이 필요합니다.")

    client: Any | None = None

    def run_candidate_ocr(source: str, candidate_content: bytes) -> str:
        nonlocal client
        if ocr_cache is not None and not refresh_ocr_cache:
            cached_text = ocr_cache.get(candidate_content)
            if cached_text is not None:
                return cached_text

        if offline:
            raise OcrCacheMissError(
                f"오프라인 OCR 캐시에 {source} 후보가 없습니다: {cache_label}"
            )

        if client is None:
            client = _get_vision_client(
                *_resolve_credential_path(credential_path)
            )
        text = _run_google_ocr(client, candidate_content)
        if ocr_cache is not None:
            ocr_cache.put(
                candidate_content,
                text,
                file_name=cache_label,
                source=source,
            )
        return text

    candidates: list[OcrCandidate] = [
        _build_candidate(
            "original",
            run_candidate_ocr("original", validated.content),
        )
    ]
    processing_warnings: list[str] = []

    # A second paid OCR request is made only when the original is not a
    # high-confidence composition. This improves difficult photos without
    # doubling every request's latency and cost.
    original = candidates[0]
    if original.parser_status != "success" or original.parser_confidence != "high":
        try:
            preprocessed = preprocess_image_bytes(validated.content)
            candidates.append(
                _build_candidate(
                    "preprocessed",
                    run_candidate_ocr("preprocessed", preprocessed),
                )
            )
        except (
            InvalidImageError,
            OcrCacheMissError,
            OcrServiceError,
            MemoryError,
        ):
            processing_warnings.append(
                "전처리 OCR에 실패하여 원본 OCR 결과를 유지했습니다."
            )

    best = max(candidates, key=lambda candidate: candidate.score)
    ocr_confidence = (
        "high"
        if best.parser_status == "success" and best.parser_confidence == "high"
        else "medium"
        if best.text
        else "low"
    )
    result_warnings = processing_warnings
    if best.source != "original":
        result_warnings.append("전처리된 이미지의 OCR 결과를 사용했습니다.")
    if not best.text:
        result_warnings.append("OCR에서 텍스트를 추출하지 못했습니다.")

    return OcrResult(
        text=best.text,
        metadata=OcrMetadata(
            source=best.source,
            confidence=ocr_confidence,
            candidate_count=len(candidates),
            image_format=validated.image_format,
            width=validated.width,
            height=validated.height,
            warnings=tuple(result_warnings),
        ),
    )


def run_ocr_with_metadata(
    image_path: str | os.PathLike[str],
    credential_path: str | None = None,
) -> OcrResult:
    return run_ocr_bytes(
        read_image_bytes(image_path),
        credential_path=credential_path,
    )


def run_ocr(
    image_path: str | os.PathLike[str],
    credential_path: str | None = None,
) -> str:
    """Compatibility wrapper for existing batch scripts."""

    return run_ocr_with_metadata(image_path, credential_path).text
