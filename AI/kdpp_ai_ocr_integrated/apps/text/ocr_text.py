"""Google Vision OCR 호출과 후보 실행을 조율하는 OCR 경계.

원본 OCR을 우선 사용하고, 파서 신뢰도가 낮을 때만 전처리 후보를 추가로
요청한다. 비용과 지연을 제한하면서 흐림·작은 글자 라벨의 인식률을 보완한다.
이미지 검증·전처리는 ``ocr_image``에, 후보 점수화는 ``ocr_candidates``에,
좌표 기반 읽기 순서 복원은 ``ocr_layout``에 둔다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.text.ocr_candidates import (
    OcrCandidate, build_candidate, find_conflicting_parts, find_unpaired_ratio_parts,
    agreed_original_composition, find_rejected_composition_parts, rotated_layout_evidence, score_candidate,
)
from apps.text.ocr_cache import OcrCacheMissError, OcrTextCache, decode_layout_words
from apps.text.ocr_errors import (
    ImageTooLargeError,
    InvalidImageError,
    OcrCompositionError,
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
    ocr_coordinate_frame,
    MAX_IMAGE_ASPECT_RATIO,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_OCR_WIDTH,
    MAX_PREPROCESSED_DIMENSION,
    MAX_PREPROCESSED_PIXELS,
    MIN_OCR_WIDTH,
    SUPPORTED_IMAGE_FORMATS,
    ValidatedImage,
    preprocess_denoised_image_bytes,
    preprocess_image_bytes,
    preprocess_reflection_image_bytes,
    preprocess_rotated_image_bytes,
    read_image_bytes,
    validate_image_bytes,
)
from apps.text.ocr_layout import (
    OcrWord, extract_response_layout_text, extract_response_words, spatial_text_from_words,
)
from apps.text.ocr_regions import (
    find_complete_material_region, find_material_region, material_region_options,
    material_region_word_boxes, prepare_material_region,
)
from apps.text.scoped_materials import read_yarn_materials

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
    "OcrCompositionError",
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
    "preprocess_denoised_image_bytes",
    "preprocess_rotated_image_bytes",
    "preprocess_reflection_image_bytes",
    "read_image_bytes",
    "reflection_ocr_enabled",
    "material_region_ocr_enabled",
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
    "denoised": 5.0,
    "rotated": 5.0,
    "material_crop": 5.0,
    "material_crop_rotated": 5.0,
}


def reflection_ocr_enabled(value: str | None = None) -> bool:
    """환경 설정값이 세 번째 반사 보정 OCR 후보를 활성화하는지 반환한다."""

    configured = os.getenv("KDPP_ENABLE_REFLECTION_OCR", "") if value is None else value
    return configured.strip().casefold() in {"1", "true", "yes", "on"}


def denoised_ocr_enabled(value: str | None = None) -> bool:
    """실패 후보 뒤의 노이즈 완화 OCR을 명시적으로 활성화한다."""

    configured = os.getenv("KDPP_ENABLE_DENOISED_OCR", "") if value is None else value
    return configured.strip().casefold() in {"1", "true", "yes", "on"}


def rotated_ocr_enabled(value: str | None = None) -> bool:
    """실패 후보 뒤의 미세 회전 OCR을 명시적으로 활성화한다."""

    configured = os.getenv("KDPP_ENABLE_ROTATED_OCR", "") if value is None else value
    return configured.strip().casefold() in {"1", "true", "yes", "on"}


def material_region_ocr_enabled(value: str | None = None) -> bool:
    """실패한 라벨의 좌표 기반 소재 영역 재인식을 기본으로 활성화한다."""

    configured = os.getenv("KDPP_ENABLE_MATERIAL_REGION_OCR", "1") if value is None else value
    return configured.strip().casefold() in {"1", "true", "yes", "on"}


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
    rpc_attempt_count: int = 0
    conflicting_parts: tuple[str, ...] = ()
    unpaired_ratio_parts: tuple[str, ...] = ()
    rejected_composition_parts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    scoped_materials: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OcrAttempt:
    """One OCR candidate attempt without provider message or credential details."""

    source: str
    outcome: str
    elapsed_ms: int
    external_call: bool
    failure_code: str = ""
    retry_count: int = 0
    rpc_attempt_count: int = 0


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
    rpc_attempt_count: int | None = None
    layout_words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True)
class _CandidateDecision:
    best: OcrCandidate
    status: str
    conflicting_parts: tuple[str, ...]
    unpaired_ratio_parts: tuple[str, ...]
    rejected_composition_parts: dict[str, tuple[str, ...]]


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


def _assess_candidates(candidates: list[OcrCandidate]) -> _CandidateDecision:
    """후보 전체의 거절 근거를 최종 파서와 같은 기준으로 판단한다."""

    best = max(candidates, key=lambda candidate: candidate.score)
    conflicting_parts = find_conflicting_parts(candidates)
    unpaired_ratio_parts = find_unpaired_ratio_parts(candidates)
    rejected_composition_parts = find_rejected_composition_parts(
        candidates, selected_part=best.selected_part,
    )
    status = best.parser_status
    if conflicting_parts or unpaired_ratio_parts or rejected_composition_parts:
        from apps.text.parse_label import parse_label

        status = parse_label(
            best.text,
            conflicting_parts=conflicting_parts,
            unpaired_ratio_parts=unpaired_ratio_parts,
            rejected_composition_parts=rejected_composition_parts,
        )["status"]
    return _CandidateDecision(
        best, status, conflicting_parts, unpaired_ratio_parts, rejected_composition_parts,
    )


def _needs_composition_retry(decision: _CandidateDecision) -> bool:
    """최종 성공은 중단하고, 연결 누락을 복원할 기회가 남으면 재시도한다."""

    from apps.text.parse_label import PART_PRIORITY

    selected = decision.best.selected_part
    if decision.status == "success":
        higher_parts = PART_PRIORITY[:PART_PRIORITY.index(selected)] if selected in PART_PRIORITY else ()
        # Preserve the confirmed fallback, but use the existing candidate budget
        # to recover a higher part whose known material simply lacks a ratio.
        return any(set(decision.rejected_composition_parts.get(part, ())) == {"unpaired_material_rows"}
                   for part in higher_parts)
    if decision.best.parser_status != "success":
        return True
    relevant_parts = set(
        PART_PRIORITY[:PART_PRIORITY.index(selected) + 1]
        if selected in PART_PRIORITY else PART_PRIORITY
    )
    # 이미 성공 문구가 있어도 확정된 상충·소재·수치 오류는 추가 OCR로
    # 해소되지 않는다. 안감의 오류는 확인된 겉감 복원을 막지 않는다.
    if relevant_parts.intersection(decision.conflicting_parts):
        return False
    if any(
        set(reasons) - {"unpaired_material_rows"}
        for part, reasons in decision.rejected_composition_parts.items()
        if part in relevant_parts
    ):
        return False
    return True


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
        raise OcrConfigurationError("Google Vision 서비스 계정 키를 찾을 수 없습니다.")
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
    deadline = time.monotonic() + timeout_seconds
    from google.api_core import exceptions as google_exceptions
    from google.api_core import retry as google_retry
    from google.cloud import vision

    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=LANGUAGE_HINTS)
    rpc_attempt_count = 0
    backoffs = google_retry.exponential_sleep_generator(
        initial=0.5, maximum=2.0, multiplier=2.0,
    )

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OcrTimeoutError("Google Vision OCR 요청 시간이 초과되었습니다.")
            rpc_attempt_count += 1
            try:
                # Disable SDK retries: each actual RPC gets the budget left
                # after previous attempts and backoff, rather than the first timeout.
                response = client.document_text_detection(
                    image=image, image_context=image_context,
                    retry=None, timeout=remaining,
                )
            except (
                google_exceptions.ServiceUnavailable,
                google_exceptions.DeadlineExceeded,
                google_exceptions.InternalServerError,
            ):
                remaining = deadline - time.monotonic()
                delay = next(backoffs)
                if remaining <= 0 or delay >= remaining:
                    raise
                time.sleep(delay)
                continue
            if time.monotonic() > deadline:
                raise OcrTimeoutError("Google Vision OCR 요청 시간이 초과되었습니다.")
            break
        words = extract_response_words(response)
        return OcrPayload(
            text=_extract_response_text(response).strip(),
            layout_text=(spatial_text_from_words(list(words)) if words
                         else _extract_response_layout_text(response)).strip(),
            retry_count=max(0, rpc_attempt_count - 1),
            rpc_attempt_count=rpc_attempt_count,
            layout_words=words,
        )
    except OcrServiceError as exc:
        exc.retry_count = max(0, rpc_attempt_count - 1)
        exc.rpc_attempt_count = rpc_attempt_count
        raise
    except OcrConfigurationError:
        raise
    except (google_exceptions.GoogleAPIError, TimeoutError) as exc:
        retry_count = max(0, rpc_attempt_count - 1)
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
                rpc_attempt_count=rpc_attempt_count,
            ) from exc
        if isinstance(cause, (google_exceptions.DeadlineExceeded, TimeoutError)):
            raise OcrTimeoutError(
                "Google Vision OCR 요청 시간이 초과되었습니다.",
                retry_count=retry_count,
                rpc_attempt_count=rpc_attempt_count,
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
                rpc_attempt_count=rpc_attempt_count,
            ) from exc
        raise OcrServiceError(
            "Google Vision OCR 요청에 실패했습니다.",
            retry_count=retry_count,
            rpc_attempt_count=rpc_attempt_count,
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
    *,
    image_key: str = "",
    image_variant_key: str = "",
    image_transform: tuple[float, ...] | None = None,
    image_region: tuple[float, ...] = (),
) -> list[OcrCandidate]:
    candidates = [_build_candidate(source, payload.text)]
    if payload.layout_text and payload.layout_text != payload.text:
        raw = candidates[0]
        layout = _build_candidate(source, payload.layout_text, layout_used=True)
        discard_layout, upright = rotated_layout_evidence(
            raw, layout, payload.layout_words, parse_candidate=_parse_candidate,
        )
        if not discard_layout:
            candidates.append(layout)
        if upright is not None:
            candidates.append(upright)
    if image_key and image_transform is not None and payload.layout_words:
        from apps.text.ocr_corrections import transform_words

        words = transform_words(payload.layout_words, image_transform)
        candidates = [replace(candidate, image_key=image_key, image_variant_key=image_variant_key, image_words=words,
                              image_region=image_region) for candidate in candidates]
        if len(candidates) == 2:
            from apps.text.ocr_candidates import literal_yarn_table_over_failed_layout

            if literal_yarn_table_over_failed_layout(candidates[0], candidates[1]):
                candidates = candidates[:1]
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
    enable_reflection: bool | None = None,
    enable_denoised: bool | None = None,
    enable_rotated: bool | None = None,
    enable_material_region: bool | None = None,
) -> OcrResult:
    """한 이미지에서 원본/전처리 OCR 후보 중 파서 관점의 최선 결과를 반환한다."""

    started_at = time.monotonic()
    validated = validate_image_bytes(
        content,
        declared_content_type=declared_content_type,
    )
    from apps.text.ocr_cache import image_sha256

    image_key = image_sha256(validated.content)

    def build_image_candidates(source: str, payload: OcrPayload, candidate_content: bytes) -> list[OcrCandidate]:
        frame = ocr_coordinate_frame(validated.content, candidate_content, source) if payload.layout_words else None
        return _build_payload_candidates(
            source, payload, image_key=image_key, image_variant_key=image_sha256(candidate_content),
            image_transform=frame[0] if frame else None,
            image_region=frame[1] if frame else (),
        )
    if offline and ocr_cache is None:
        raise OcrCacheMissError("오프라인 OCR 실행에는 캐시 파일이 필요합니다.")
    use_reflection = (
        reflection_ocr_enabled()
        if enable_reflection is None
        else enable_reflection
    )
    use_denoised = (
        denoised_ocr_enabled() if enable_denoised is None else enable_denoised
    )
    use_rotated = rotated_ocr_enabled() if enable_rotated is None else enable_rotated
    use_material_region = (
        material_region_ocr_enabled() if enable_material_region is None else enable_material_region
    )

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
        candidate_deadline = time.monotonic() + timeout_seconds
        # QA 재실행에서 동일 이미지에 대한 외부 OCR 호출과 비용을 피한다.
        if ocr_cache is not None and not refresh_ocr_cache:
            cached_entry = ocr_cache.get_entry(candidate_content)
            if cached_entry is not None:
                words = decode_layout_words(cached_entry)
                return OcrPayload(
                    text=cached_entry["text"],
                    layout_text=(spatial_text_from_words(list(words)) if words
                                 else str(cached_entry.get("layout_text", ""))),
                    layout_words=words,
                )

        if offline:
            raise OcrCacheMissError(
                f"오프라인 OCR 캐시에 {source} 후보가 없습니다: {cache_label}"
            )

        if client is None:
            client = _get_vision_client(
                *_resolve_credential_path(credential_path)
            )
        remaining = min(
            candidate_deadline - time.monotonic(), remaining_timeout_seconds(),
        )
        if remaining <= 0:
            error_type = (
                OcrTotalTimeoutError if remaining_timeout_seconds() <= 0 else OcrTimeoutError
            )
            raise error_type("OCR 요청 시간 제한을 초과했습니다.", rpc_attempt_count=0)
        external_call_count += 1
        try:
            payload = _coerce_ocr_payload(
                _run_google_ocr(
                    client,
                    candidate_content,
                    timeout_seconds=remaining,
                )
            )
        except OcrServiceError as exc:
            if exc.rpc_attempt_count == 0:
                external_call_count -= 1
            raise
        if ocr_cache is not None:
            ocr_cache.put(
                candidate_content,
                payload.text,
                file_name=cache_label,
                source=source,
                layout_text=payload.layout_text,
                layout_words=payload.layout_words,
            )
        return payload

    def run_tracked_candidate(source: str, candidate_content: bytes) -> OcrPayload:
        """Measure each candidate without exposing provider exception messages."""

        external_calls_before = external_call_count

        def rpc_count(value: OcrPayload | Exception) -> int:
            count = getattr(value, "rpc_attempt_count", None)
            if count is not None:
                return count
            # Older text-only test doubles represent one RPC plus actual retries.
            return (
                1 + getattr(value, "retry_count", 0)
                if external_call_count > external_calls_before else 0
            )
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
                    rpc_attempt_count=rpc_count(exc),
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
                    rpc_attempt_count=rpc_count(payload),
                )
            )
            return payload

    candidates = build_image_candidates(
        "original",
        run_tracked_candidate("original", validated.content),
        validated.content,
    )
    ocr_candidate_count = 1

    # 같은 응답의 원문·좌표 조성이 확인됐으면 줄 연결의 중간 신뢰도만으로
    # 재호출하지 않는다. 관측된 충돌·누락의 최종 안전 판정은 계속 우선한다.
    decision = _assess_candidates(candidates)
    original = decision.best
    early_region = None
    early_rotated = False
    # A complete crop can avoid turning a clipped care/composition heading
    # into opaque full-image preprocessing output in the first place.
    if use_material_region and decision.status != "success":
        located_region = find_material_region(candidates, validated.width, validated.height)
        if located_region is not None:
            early_region = find_complete_material_region(candidates, located_region)
        if early_region is not None:
            source = "material_crop_rotated"
            early_rotated = True
            try:
                if remaining_timeout_seconds() <= 0:
                    record_total_timeout(source)
                    raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
                font_height, rotation_degrees = material_region_options(candidates, early_region)
                cropped = prepare_material_region(
                    validated.content, early_region, rotated=True,
                    font_height=font_height, rotation_degrees=rotation_degrees,
                    word_boxes=material_region_word_boxes(candidates, early_region),
                )
                payload = run_tracked_candidate(source, cropped.content)
                candidates.extend(_build_payload_candidates(
                    source, payload, image_key=image_key,
                    image_variant_key=image_sha256(cropped.content),
                    image_transform=cropped.transform, image_region=cropped.region,
                ))
                ocr_candidate_count += 1
            except (InvalidImageError, OcrCacheMissError, OcrServiceError, MemoryError) as exc:
                if not isinstance(exc, OcrTotalTimeoutError):
                    attempt_failures.append(f"{source}:{type(exc).__name__}")
                    processing_warnings.append("소재 영역 재인식에 실패하여 기존 후보를 유지했습니다.")
            decision = _assess_candidates(candidates)
    if not (early_rotated and decision.status == "success") and (
        original.parser_status != "success"
        or (original.parser_confidence != "high" and not agreed_original_composition(candidates))
        or _needs_composition_retry(decision)
    ):
        try:
            if remaining_timeout_seconds() <= 0:
                record_total_timeout("preprocessed")
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            preprocessed = preprocess_image_bytes(validated.content)
            if remaining_timeout_seconds() <= 0:
                record_total_timeout("preprocessed")
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            candidates.extend(
                build_image_candidates(
                    "preprocessed",
                    run_tracked_candidate("preprocessed", preprocessed),
                    preprocessed,
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
            # 기본 전처리 후에도 최종 판단이 복원 가능한 실패이면 추가한다.
            if use_reflection and _needs_composition_retry(_assess_candidates(candidates)):
                try:
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout("reflection")
                        raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
                    reflection = preprocess_reflection_image_bytes(validated.content)
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout("reflection")
                        raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
                    candidates.extend(
                        build_image_candidates(
                            "reflection",
                            run_tracked_candidate("reflection", reflection),
                            reflection,
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

    for source, enabled, preprocess, failure_warning in (
        (
            "denoised", use_denoised, preprocess_denoised_image_bytes,
            "노이즈 완화 OCR에 실패하여 기존 후보를 유지했습니다.",
        ),
        (
            "rotated", use_rotated, preprocess_rotated_image_bytes,
            "미세 회전 OCR에 실패하여 기존 후보를 유지했습니다.",
        ),
    ):
        if not enabled or not _needs_composition_retry(_assess_candidates(candidates)):
            continue
        try:
            if remaining_timeout_seconds() <= 0:
                record_total_timeout(source)
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            processed = preprocess(validated.content)
            if remaining_timeout_seconds() <= 0:
                record_total_timeout(source)
                raise OcrTotalTimeoutError("전체 OCR 시간 제한을 초과했습니다.")
            candidates.extend(
                build_image_candidates(
                    source,
                    run_tracked_candidate(source, processed),
                    processed,
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
                attempt_failures.append(f"{source}:{type(exc).__name__}")
                processing_warnings.append(failure_warning)

    if use_material_region and _assess_candidates(candidates).status != "success":
        region = early_region or find_material_region(candidates, validated.width, validated.height)
        if region is not None:
            complete_region = find_complete_material_region(candidates, region)
            if complete_region is not None:
                region = complete_region
            font_height, rotation_degrees = material_region_options(candidates, region)
            word_boxes = material_region_word_boxes(candidates, region)
            # A clipped heading can manufacture opaque OCR characters. Use
            # the complete crop's rotated reading first, then the plain crop
            # only if its independent response is still needed.
            for rotated in ((True, False) if complete_region is not None else (False, True)):
                if rotated and early_rotated:
                    continue
                if _assess_candidates(candidates).status == "success":
                    break
                source = "material_crop_rotated" if rotated else "material_crop"
                try:
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout(source)
                        break
                    cropped = prepare_material_region(
                        validated.content, region, rotated=rotated,
                        font_height=font_height, rotation_degrees=rotation_degrees,
                        word_boxes=word_boxes,
                        enhancement=(("mild_contrast" if _prefer_mild_region_contrast(candidates)
                                      else "adaptive_mild") if rotated and complete_region is None else "standard"),
                    )
                    if remaining_timeout_seconds() <= 0:
                        record_total_timeout(source)
                        break
                    payload = run_tracked_candidate(source, cropped.content)
                    candidates.extend(_build_payload_candidates(
                        source, payload, image_key=image_key,
                        image_variant_key=image_sha256(cropped.content),
                        image_transform=cropped.transform, image_region=cropped.region,
                    ))
                    ocr_candidate_count += 1
                except (
                    InvalidImageError,
                    OcrCacheMissError,
                    OcrServiceError,
                    MemoryError,
                ) as exc:
                    if isinstance(exc, OcrTotalTimeoutError):
                        break
                    attempt_failures.append(f"{source}:{type(exc).__name__}")
                    processing_warnings.append(
                        "소재 영역 재인식에 실패하여 기존 후보를 유지했습니다."
                    )

    decision = _assess_candidates(candidates)
    best = decision.best
    conflicting_parts = decision.conflicting_parts
    unpaired_ratio_parts = decision.unpaired_ratio_parts
    rejected_composition_parts = decision.rejected_composition_parts
    rejected_representative = decision.status != "success" and bool(
        conflicting_parts or unpaired_ratio_parts or rejected_composition_parts
    )
    ocr_confidence = (
        "low"
        if rejected_representative
        or best.selected_part in (*conflicting_parts, *unpaired_ratio_parts)
        or ((conflicting_parts or unpaired_ratio_parts) and best.parser_status != "success")
        else "high"
        if best.parser_status == "success" and best.parser_confidence == "high"
        else "medium"
        if best.text
        else "low"
    )
    result_warnings = processing_warnings
    if best.source != "original":
        if best.source == "reflection":
            result_warnings.append("반사 보정된 이미지의 OCR 결과를 사용했습니다.")
        elif best.source == "denoised":
            result_warnings.append("노이즈를 완화한 이미지의 OCR 결과를 사용했습니다.")
        elif best.source == "rotated":
            result_warnings.append("미세 회전한 이미지의 OCR 결과를 사용했습니다.")
        elif best.source.startswith("material_crop"):
            result_warnings.append("확대한 소재 영역의 OCR 결과를 사용했습니다.")
        else:
            result_warnings.append("전처리된 이미지의 OCR 결과를 사용했습니다.")
    if best.layout_used:
        result_warnings.append("OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다.")
    if not best.text:
        result_warnings.append("OCR에서 텍스트를 추출하지 못했습니다.")

    # A crop can omit the YARN heading. Preserve observations from the full
    # original response without changing candidate choice or primary status.
    scoped_materials = {}
    for candidate in candidates:
        if candidate.source == "original" and not candidate.layout_used:
            observation = read_yarn_materials(candidate.text)
            if observation is not None:
                scoped_materials = {**observation, "source": "original", "image_key": candidate.image_key}
                break

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
            rpc_attempt_count=sum(attempt.rpc_attempt_count for attempt in attempts),
            conflicting_parts=conflicting_parts,
            unpaired_ratio_parts=unpaired_ratio_parts,
            rejected_composition_parts=rejected_composition_parts,
            scoped_materials=scoped_materials,
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
    """문자열 전용 연동에서도 대표 부위가 충돌하면 성공 텍스트로 넘기지 않는다."""

    result = run_ocr_with_metadata(image_path, credential_path)
    if (
        result.metadata.conflicting_parts or result.metadata.unpaired_ratio_parts
        or result.metadata.rejected_composition_parts
    ):
        from apps.text.parse_label import parse_label

        parsed = parse_label(
            result.text,
            conflicting_parts=result.metadata.conflicting_parts,
            unpaired_ratio_parts=result.metadata.unpaired_ratio_parts,
            rejected_composition_parts=result.metadata.rejected_composition_parts,
        )
        if parsed["status"] != "success":
            raise OcrCompositionError(parsed["message"])
    return result.text


def _prefer_mild_region_contrast(candidates: list[OcrCandidate]) -> bool:
    """실제 한글 소재가 읽힌 단일 조성에서 누락된 가는 획 보정을 우선한다."""
    import re

    from apps.text.ratio_contract import has_exact_total
    from apps.text.material_extraction import extract_materials

    for candidate in candidates:
        ratios = candidate.observed_ratios.get("generic", [])
        materials = candidate.observed_materials.get("generic", [])
        reasons = candidate.rejected_composition_parts.get("generic", ())
        if (
            reasons and set(reasons) <= {"unpaired_material_rows", "unresolved_material_token"}
            and not candidate.conflicting_parts
            and set(candidate.observed_ratios) == {"generic"}
            and set(candidate.observed_materials) <= {"generic"}
            and 2 <= len(ratios) <= 3 and 0 < len(materials) < len(ratios)
            and all(0 < ratio <= 100 for ratio in ratios) and has_exact_total(ratios)
            and any(extract_materials(token) for token in re.findall(r"[가-힣]+", candidate.text))
        ):
            return True
    return False
