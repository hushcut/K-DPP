"""Google Vision OCR 호출과 후보 실행을 조율하는 OCR 경계.

원본 OCR을 우선 사용하고, 파서 신뢰도가 낮을 때만 전처리 후보를 추가로
요청한다. 비용과 지연을 제한하면서 흐림·작은 글자 라벨의 인식률을 보완한다.
이미지 검증·전처리는 ``ocr_image``에, 후보 점수화는 ``ocr_candidates``에,
좌표 기반 읽기 순서 복원은 ``ocr_layout``에 둔다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.text.ocr_candidates import OcrCandidate, build_candidate, score_candidate
from apps.text.ocr_cache import OcrCacheMissError, OcrTextCache
from apps.text.ocr_errors import (
    ImageTooLargeError,
    InvalidImageError,
    OcrConfigurationError,
    OcrError,
    OcrQuotaExceededError,
    OcrServiceError,
    OcrTimeoutError,
    OcrTotalTimeoutError,
    OcrUnavailableError,
    UnsupportedImageError,
)
from apps.text.ocr_image import (
    MAX_IMAGE_ASPECT_RATIO,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_OCR_WIDTH,
    MAX_PREPROCESSED_DIMENSION,
    MAX_PREPROCESSED_PIXELS,
    MIN_OCR_WIDTH,
    SUPPORTED_IMAGE_FORMATS,
    ValidatedImage,
    preprocess_image_bytes,
    preprocess_reflection_image_bytes,
    read_image_bytes,
    validate_image_bytes,
)
from apps.text.ocr_layout import OcrWord, extract_response_layout_text, spatial_text_from_words

__all__ = [
    "ImageTooLargeError",
    "InvalidImageError",
    "MAX_IMAGE_ASPECT_RATIO",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_PIXELS",
    "MAX_OCR_WIDTH",
    "MAX_PREPROCESSED_DIMENSION",
    "MAX_PREPROCESSED_PIXELS",
    "MIN_OCR_WIDTH",
    "OcrConfigurationError",
    "OcrError",
    "OcrMetadata",
    "OcrQuotaExceededError",
    "OcrResult",
    "OcrServiceError",
    "OcrTimeoutError",
    "OcrUnavailableError",
    "SUPPORTED_IMAGE_FORMATS",
    "UnsupportedImageError",
    "ValidatedImage",
    "preprocess_image_bytes",
    "preprocess_reflection_image_bytes",
    "read_image_bytes",
    "run_ocr",
    "run_ocr_bytes",
    "run_ocr_with_metadata",
    "validate_image_bytes",
]

LANGUAGE_HINTS = ["ko", "en", "ja", "zh-Hans", "zh-Hant"]
OCR_TIMEOUT_SECONDS = 20
OCR_TOTAL_TIMEOUT_SECONDS = 25.0
OCR_CANDIDATE_TIMEOUT_SECONDS = {
    "original": 10.0,
    "preprocessed": 8.0,
    "reflection": 7.0,
}


@dataclass(frozen=True)
class OcrMetadata:
    source: str
    confidence: str
    candidate_count: int
    image_format: str
    width: int
    height: int
    warnings: tuple[str, ...] = ()
    attempt_failures: tuple[str, ...] = ()
    attempt_count: int = 0
    external_call_count: int = 0
    retry_count: int = 0
    elapsed_ms: int = 0
    attempts: tuple["OcrAttempt", ...] = ()


@dataclass(frozen=True)
class OcrAttempt:
    """One OCR candidate attempt without provider message or credential details."""

    source: str
    outcome: str
    elapsed_ms: int
    external_call: bool
    failure_code: str = ""
    retry_count: int = 0


@dataclass(frozen=True)
class OcrResult:
    text: str
    metadata: OcrMetadata


@dataclass(frozen=True)
class OcrPayload:
    """Raw OCR text plus a text order reconstructed from word coordinates."""

    text: str
    layout_text: str = ""
    retry_count: int = 0


def _parse_candidate(text: str) -> dict:
    from apps.text.parse_label import parse_label

    return parse_label(text)


def _score_candidate(
    text: str,
    materials: dict[str, float | int],
    selected_part: str,
    parser_status: str,
    parser_confidence: str,
    source: str,
    *,
    ratio_total_before_normalization: float | None,
    warning_count: int,
) -> tuple[int, int, int, int, float, int, int, int]:
    return score_candidate(
        text,
        materials,
        selected_part,
        parser_status,
        parser_confidence,
        source,
        ratio_total_before_normalization=ratio_total_before_normalization,
        warning_count=warning_count,
    )


def _build_candidate(
    source: str,
    text: str,
    *,
    layout_used: bool = False,
) -> OcrCandidate:
    return build_candidate(
        source,
        text,
        parse_candidate=_parse_candidate,
        layout_used=layout_used,
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


def _spatial_text_from_words(words: list[OcrWord]) -> str:
    return spatial_text_from_words(words)


def _extract_response_layout_text(response: Any) -> str:
    return extract_response_layout_text(response)


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


def _run_google_ocr(
    client: Any,
    content: bytes,
    *,
    timeout_seconds: float = OCR_TIMEOUT_SECONDS,
) -> OcrPayload:
    from google.api_core import exceptions as google_exceptions
    from google.api_core import retry as google_retry
    from google.cloud import vision

    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=LANGUAGE_HINTS)
    retry_count = 0

    def record_retry(_exc: Exception) -> None:
        nonlocal retry_count
        retry_count += 1

    retry = google_retry.Retry(
        predicate=google_retry.if_exception_type(
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError,
        ),
        initial=0.5,
        maximum=2.0,
        multiplier=2.0,
        deadline=timeout_seconds,
        on_error=record_retry,
    )

    try:
        response = client.document_text_detection(
            image=image,
            image_context=image_context,
            retry=retry,
            timeout=timeout_seconds,
        )
        return OcrPayload(
            text=_extract_response_text(response).strip(),
            layout_text=_extract_response_layout_text(response).strip(),
            retry_count=retry_count,
        )
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
                "Google Vision OCR 사용량 한도를 초과했습니다.",
                retry_count=retry_count,
            ) from exc
        if isinstance(cause, (google_exceptions.DeadlineExceeded, TimeoutError)):
            raise OcrTimeoutError(
                "Google Vision OCR 요청 시간이 초과되었습니다.",
                retry_count=retry_count,
            ) from exc
        if isinstance(
            cause,
            (
                google_exceptions.ServiceUnavailable,
                google_exceptions.InternalServerError,
            ),
        ):
            raise OcrUnavailableError(
                "Google Vision OCR 서비스를 일시적으로 사용할 수 없습니다.",
                retry_count=retry_count,
            ) from exc
        raise OcrServiceError(
            "Google Vision OCR 요청에 실패했습니다.",
            retry_count=retry_count,
        ) from exc


def _coerce_ocr_payload(value: OcrPayload | str) -> OcrPayload:
    """Keep test doubles and older callers that return plain text compatible."""

    if isinstance(value, OcrPayload):
        return value
    if isinstance(value, str):
        return OcrPayload(text=value)
    raise TypeError("OCR 결과는 텍스트 또는 OcrPayload여야 합니다.")


def _build_payload_candidates(
    source: str,
    payload: OcrPayload,
) -> list[OcrCandidate]:
    candidates = [_build_candidate(source, payload.text)]
    if payload.layout_text and payload.layout_text != payload.text:
        candidates.append(
            _build_candidate(source, payload.layout_text, layout_used=True)
        )
    return candidates


def _attempt_failure_code(exc: Exception) -> str:
    """Return a stable, non-sensitive code for QA diagnostics."""

    if isinstance(exc, OcrQuotaExceededError):
        return "quota_exceeded"
    if isinstance(exc, OcrTimeoutError):
        return "timeout"
    if isinstance(exc, OcrUnavailableError):
        return "service_unavailable"
    if isinstance(exc, OcrCacheMissError):
        return "cache_miss"
    if isinstance(exc, ImageTooLargeError):
        return "image_too_large"
    if isinstance(exc, InvalidImageError):
        return "invalid_image"
    if isinstance(exc, OcrServiceError):
        return "service_error"
    if isinstance(exc, MemoryError):
        return "memory_error"
    return "unknown"


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
    """한 이미지에서 원본/전처리 OCR 후보 중 파서 관점의 최선 결과를 반환한다."""

    started_at = time.monotonic()
    validated = validate_image_bytes(
        content,
        declared_content_type=declared_content_type,
    )
    if offline and ocr_cache is None:
        raise OcrCacheMissError("오프라인 OCR 실행에는 캐시 파일이 필요합니다.")

    client: Any | None = None
    external_call_count = 0
    attempts: list[OcrAttempt] = []
    processing_warnings: list[str] = []
    attempt_failures: list[str] = []

    def remaining_timeout_seconds() -> float:
        return max(0.0, OCR_TOTAL_TIMEOUT_SECONDS - (time.monotonic() - started_at))

    def record_total_timeout(source: str) -> None:
        attempts.append(
            OcrAttempt(
                source=source,
                outcome="skipped",
                elapsed_ms=0,
                external_call=False,
                failure_code="total_timeout",
            )
        )
        attempt_failures.append(f"{source}:total_timeout")
        processing_warnings.append(
            "전체 OCR 시간 제한으로 추가 후보를 실행하지 않았습니다."
        )

    def run_candidate_ocr(
        source: str,
        candidate_content: bytes,
        *,
        timeout_seconds: float,
    ) -> OcrPayload:
        nonlocal client, external_call_count
        # QA 재실행에서 동일 이미지에 대한 외부 OCR 호출과 비용을 피한다.
        if ocr_cache is not None and not refresh_ocr_cache:
            cached_entry = ocr_cache.get_entry(candidate_content)
            if cached_entry is not None:
                return OcrPayload(
                    text=cached_entry["text"],
                    layout_text=str(cached_entry.get("layout_text", "")),
                )

        if offline:
            raise OcrCacheMissError(
                f"오프라인 OCR 캐시에 {source} 후보가 없습니다: {cache_label}"
            )

        if client is None:
            client = _get_vision_client(
                *_resolve_credential_path(credential_path)
            )
        external_call_count += 1
        payload = _coerce_ocr_payload(
            _run_google_ocr(
                client,
                candidate_content,
                timeout_seconds=timeout_seconds,
            )
        )
        if ocr_cache is not None:
            ocr_cache.put(
                candidate_content,
                payload.text,
                file_name=cache_label,
                source=source,
                layout_text=payload.layout_text,
            )
        return payload

    def run_tracked_candidate(source: str, candidate_content: bytes) -> OcrPayload:
        """Measure each candidate without exposing provider exception messages."""

        external_calls_before = external_call_count
        attempt_started_at = time.monotonic()
        timeout_seconds = min(
            OCR_CANDIDATE_TIMEOUT_SECONDS[source],
            remaining_timeout_seconds(),
        )
        if timeout_seconds <= 0:
            record_total_timeout(source)
            raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
        try:
            payload = run_candidate_ocr(
                source,
                candidate_content,
                timeout_seconds=timeout_seconds,
            )
        except (
            InvalidImageError,
            OcrCacheMissError,
            OcrServiceError,
            MemoryError,
        ) as exc:
            attempts.append(
                OcrAttempt(
                    source=source,
                    outcome="failed",
                    elapsed_ms=round((time.monotonic() - attempt_started_at) * 1000),
                    external_call=external_call_count > external_calls_before,
                    failure_code=_attempt_failure_code(exc),
                    retry_count=getattr(exc, "retry_count", 0),
                )
            )
            raise
        else:
            attempts.append(
                OcrAttempt(
                    source=source,
                    outcome="success",
                    elapsed_ms=round((time.monotonic() - attempt_started_at) * 1000),
                    external_call=external_call_count > external_calls_before,
                    retry_count=payload.retry_count,
                )
            )
            return payload

    candidates = _build_payload_candidates(
        "original",
        run_tracked_candidate("original", validated.content),
    )
    ocr_candidate_count = 1

    # 원본 파싱이 충분히 신뢰할 만할 때는 전처리 OCR 호출을 생략한다.
    # 어려운 사진만 재시도해 비용과 지연을 제한한다.
    original = max(candidates, key=lambda candidate: candidate.score)
    if original.parser_status != "success" or original.parser_confidence != "high":
        try:
            if remaining_timeout_seconds() <= 0:
                record_total_timeout("preprocessed")
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            preprocessed = preprocess_image_bytes(validated.content)
            if remaining_timeout_seconds() <= 0:
                record_total_timeout("preprocessed")
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            candidates.extend(
                _build_payload_candidates(
                    "preprocessed",
                    run_tracked_candidate("preprocessed", preprocessed),
                )
            )
            ocr_candidate_count += 1
        except (
            InvalidImageError,
            OcrCacheMissError,
            OcrServiceError,
            MemoryError,
        ) as exc:
            if not isinstance(exc, OcrTotalTimeoutError):
                attempt_failures.append(f"preprocessed:{type(exc).__name__}")
                processing_warnings.append(
                    "전처리 OCR에 실패하여 원본 OCR 결과를 유지했습니다."
                )
        else:
            # 기본 전처리까지 조성을 만들지 못한 경우에만 반사 보정 후보를
            # 추가한다. 성공한 후보가 있으면 불필요한 Vision 호출을 하지 않는다.
            if not any(
                candidate.parser_status == "success" for candidate in candidates
            ):
                try:
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout("reflection")
                        raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
                    reflection = preprocess_reflection_image_bytes(validated.content)
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout("reflection")
                        raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
                    candidates.extend(
                        _build_payload_candidates(
                            "reflection",
                            run_tracked_candidate("reflection", reflection),
                        )
                    )
                    ocr_candidate_count += 1
                except (
                    InvalidImageError,
                    OcrCacheMissError,
                    OcrServiceError,
                    MemoryError,
                ) as exc:
                    if not isinstance(exc, OcrTotalTimeoutError):
                        attempt_failures.append(f"reflection:{type(exc).__name__}")
                        processing_warnings.append(
                            "반사 보정 OCR에 실패하여 기존 후보를 유지했습니다."
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
        if best.source == "reflection":
            result_warnings.append("반사 보정된 이미지의 OCR 결과를 사용했습니다.")
        else:
            result_warnings.append("전처리된 이미지의 OCR 결과를 사용했습니다.")
    if best.layout_used:
        result_warnings.append("OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다.")
    if not best.text:
        result_warnings.append("OCR에서 텍스트를 추출하지 못했습니다.")

    return OcrResult(
        text=best.text,
        metadata=OcrMetadata(
            source=best.source,
            confidence=ocr_confidence,
            candidate_count=ocr_candidate_count,
            image_format=validated.image_format,
            width=validated.width,
            height=validated.height,
            warnings=tuple(result_warnings),
            attempt_failures=tuple(attempt_failures),
            attempt_count=len(attempts),
            external_call_count=external_call_count,
            retry_count=sum(attempt.retry_count for attempt in attempts),
            elapsed_ms=round((time.monotonic() - started_at) * 1000),
            attempts=tuple(attempts),
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
