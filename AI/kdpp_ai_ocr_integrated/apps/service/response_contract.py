"""프론트엔드와 공유하는 라벨 분석 응답 계약.

성공·실패·OCR 예외에서 같은 기본 키를 유지해 소비자가 존재 여부를 매번
확인하지 않도록 한다. 새 응답 필드는 여기와 테스트를 함께 갱신한다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from apps.text.ratio_contract import has_exact_total


def _require_json_number(value: Any) -> int | float:
    """문자열·불리언·자동 변환이 필요한 객체를 혼용률 숫자로 받아들이지 않는다."""

    if type(value) not in (int, float):
        raise ValueError("혼용률은 정수 또는 실수여야 합니다.")
    return value


MaterialRatio = Annotated[
    int | float,
    BeforeValidator(_require_json_number),
    Field(gt=0, le=100, allow_inf_nan=False),
]

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


class LabelResponseContract(BaseModel):
    """항상 제공하는 응답 필드를 검증하며 추가 OCR·파서 근거 필드는 허용한다."""

    model_config = ConfigDict(extra="allow", strict=True)

    api_version: str
    status: Literal["success", "failed"]
    error_code: str = ""
    message: str = ""
    materials: dict[str, MaterialRatio] = Field(default_factory=dict)
    materials_korean: str = ""
    raw_ocr_preview: str = ""
    confidence: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    care_instruction: str = ""
    care_instructions: list[str] = Field(default_factory=list)
    selected_part: str = ""
    parts: dict[str, dict[str, MaterialRatio]] = Field(default_factory=dict)
    parse_evidence: dict[str, Any] = Field(default_factory=dict)
    ocr: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_compositions(self) -> LabelResponseContract:
        """성공 조성의 합계와 대표 부위가 파서의 확정 기준에 맞는지 검사한다."""

        for part, materials in self.parts.items():
            if not has_exact_total(materials.values()):
                raise ValueError(f"parts.{part}의 혼용률 합계는 100이어야 합니다.")
        if self.status == "failed":
            if self.materials or self.parts or self.selected_part:
                raise ValueError("실패 응답에는 확정 소재나 선택 부위를 포함할 수 없습니다.")
        else:
            if not has_exact_total(self.materials.values()):
                raise ValueError("성공 응답 materials의 혼용률 합계는 100이어야 합니다.")
            if self.parts or self.selected_part:
                if self.parts.get(self.selected_part) != self.materials:
                    raise ValueError("materials는 selected_part의 조성과 일치해야 합니다.")
        return self


def normalize_label_response(
    payload: dict[str, Any],
    *,
    api_version: str,
) -> dict[str, Any]:
    """성공·실패 응답을 검증하고 중첩 컬렉션까지 독립된 복사본으로 반환한다."""

    result = deepcopy({**LABEL_RESPONSE_DEFAULTS, **payload, "api_version": api_version})
    raw_confidence = result["confidence"]

    result["confidence"] = (
        {
            **LABEL_RESPONSE_DEFAULTS["confidence"],
            **raw_confidence,
        }
        if isinstance(raw_confidence, dict)
        else raw_confidence
    )
    # 엄격히 검증하되 모델로 재직렬화하지 않아 기존 정수·소수 표기를 보존한다.
    LabelResponseContract.model_validate(result)
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
        {**(extra or {}), "status": "failed", "error_code": error_code, "message": message},
        api_version=api_version,
    )
