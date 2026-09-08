"""프론트엔드와 공유하는 라벨 분석 응답 계약.

성공·실패·OCR 예외에서 같은 기본 키를 유지해 소비자가 존재 여부를 매번
확인하지 않도록 한다. 새 응답 필드는 여기와 테스트를 함께 갱신한다.
"""

from __future__ import annotations

from typing import Any

# API 응답에서 항상 제공하는 기본 키. 값이 없을 때도 타입은 유지한다.
LABEL_RESPONSE_DEFAULTS: dict[str, Any] = {
    "error_code": "",
    "message": "",
    "materials": {},
    "materials_korean": "",
    "raw_ocr_preview": "",
    "confidence": {"ocr": "unknown", "parser": "low"},
    "warnings": [],
    "care_instruction": "",
    "care_instructions": [],
    "selected_part": "",
    "parts": {},
    "parse_evidence": {},
    "ocr": {},
}


def normalize_label_response(
    payload: dict[str, Any],
    *,
    api_version: str,
) -> dict[str, Any]:
    """Return the stable label-analysis schema for both success and failure."""

    # 얕은 병합 뒤 중첩 컬렉션은 별도로 복사해 호출자가 기본값을 변경하지 못하게 한다.
    result = {"api_version": api_version, **LABEL_RESPONSE_DEFAULTS, **payload}
    result["confidence"] = {
        **LABEL_RESPONSE_DEFAULTS["confidence"],
        **dict(payload.get("confidence", {})),
    }
    result["warnings"] = list(payload.get("warnings", []))
    result["care_instructions"] = list(payload.get("care_instructions", []))
    result["parts"] = dict(payload.get("parts", {}))
    result["parse_evidence"] = dict(payload.get("parse_evidence", {}))
    result["ocr"] = dict(payload.get("ocr", {}))
    return result


def failed_label_response(
    *,
    api_version: str,
    error_code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """실패 원인을 유지하면서도 성공과 같은 응답 형태를 반환한다."""

    return normalize_label_response(
        {"status": "failed", "error_code": error_code, "message": message, **(extra or {})},
        api_version=api_version,
    )
