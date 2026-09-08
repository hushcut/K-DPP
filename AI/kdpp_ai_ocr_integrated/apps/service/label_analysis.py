"""OCR 결과와 라벨 파서를 연결해 서비스 응답으로 만드는 조립 계층.

OCR 모듈은 텍스트와 이미지 처리 메타데이터만 담당하고, 파서는 소재·혼용률
해석만 담당한다. 이 파일은 두 결과를 안정적인 API 응답 계약으로 합친다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from apps.text.ocr_text import (
    OcrMetadata,
    OcrResult,
    read_image_bytes,
    run_ocr_bytes,
)
from apps.text.parse_label import parse_label
from apps.service.response_contract import normalize_label_response

API_VERSION = "1.0"


def _merge_ocr_metadata(parsed: dict[str, Any], metadata: OcrMetadata) -> dict[str, Any]:
    """파서 결과에 OCR 출처와 신뢰도 정보를 덧붙인다."""

    # 먼저 누락 필드를 채워 성공·실패 응답의 형태를 동일하게 만든다.
    result = normalize_label_response(parsed, api_version=API_VERSION)
    confidence = dict(result.get("confidence", {}))
    confidence["ocr"] = metadata.confidence
    result["confidence"] = confidence

    warnings = list(result.get("warnings", []))
    for warning in metadata.warnings:
        if warning not in warnings:
            warnings.append(warning)
    result["warnings"] = warnings
    # 원문 전체는 raw_ocr_preview로 제한하고, 여기에는 재현에 필요한 메타데이터만 둔다.
    result["ocr"] = {
        "source": metadata.source,
        "candidate_count": metadata.candidate_count,
        "image_format": metadata.image_format,
        "width": metadata.width,
        "height": metadata.height,
    }
    return result


def analyze_ocr_result(ocr_result: OcrResult) -> dict[str, Any]:
    """이미 OCR이 끝난 결과를 파싱한다. QA에서는 외부 OCR 호출 없이 이 함수를 쓴다."""

    return _merge_ocr_metadata(
        parse_label(ocr_result.text),
        ocr_result.metadata,
    )


def analyze_label_image_bytes(
    content: bytes,
    *,
    credential_path: str | None = None,
    declared_content_type: str | None = None,
) -> dict[str, Any]:
    """HTTP 업로드 바이트의 표준 처리 순서: OCR -> 파싱 -> 응답 계약 정규화."""

    ocr_result = run_ocr_bytes(
        content,
        credential_path=credential_path,
        declared_content_type=declared_content_type,
    )
    return analyze_ocr_result(ocr_result)


def analyze_label_image(
    image_path: str | os.PathLike[str],
    *,
    credential_path: str | None = None,
) -> dict[str, Any]:
    return analyze_label_image_bytes(
        read_image_bytes(Path(image_path)),
        credential_path=credential_path,
    )


def analyze_label_text(text: str) -> dict[str, Any]:
    """Parse already-extracted OCR text without claiming OCR confidence."""

    return normalize_label_response(parse_label(text), api_version=API_VERSION)
