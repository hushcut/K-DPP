"""OCR 결과와 라벨 파서를 연결해 서비스 응답으로 만드는 조립 계층.

OCR 모듈은 텍스트와 이미지 처리 메타데이터만 담당하고, 파서는 소재·혼용률
해석만 담당한다. 이 파일은 두 결과를 안정적인 API 응답 계약으로 합친다.
"""

from __future__ import annotations

import os
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from apps.text.ocr_text import (
    OcrMetadata,
    OcrResult,
    read_image_bytes,
    run_ocr_bytes,
)
from apps.text.parse_label import parse_label
from apps.text.line_analysis_cache import line_analysis_scope
from apps.service.response_contract import normalize_label_response

API_VERSION = "1.0"

_PUBLIC_PART_NAMES = {
    "outer": "outer",
    "outer_2": "outer_2",
    "generic": "unidentified",
    "lining": "lining",
    "filling": "filling",
    "pocket": "pocket",
    "rib": "rib",
    "sleeve": "sleeve",
    "color_block": "color_block",
    "embroidery_yarn": "embroidery_yarn",
}


def _with_public_guidance(parsed: dict[str, Any]) -> dict[str, Any]:
    """최종 부위·재촬영 근거만 공개 코드로 전달하고 원래 판정은 유지한다."""

    warnings = [warning for warning in parsed.get("warnings", [])
                if not warning.startswith(("composition_part:", "composition_action:"))]
    if parsed.get("status") == "success":
        part = _PUBLIC_PART_NAMES.get(parsed.get("selected_part"), "unidentified")
        warnings.append(f"composition_part:{part}")
    elif (parsed.get("status") == "failed"
          and parsed.get("parse_evidence", {}).get("recapture", {}).get("action")
          == "retake_composition_region"):
        warnings.append("composition_action:retake_composition_region")
    return {**parsed, "warnings": warnings}


def _with_part_uncertainty(parsed: dict[str, Any]) -> dict[str, Any]:
    """확정 소재와 부위 미확정을 구분하되 후보 선택에는 영향을 주지 않는다."""

    if parsed.get("status") != "success" or parsed.get("selected_part") != "generic":
        return parsed
    result = dict(parsed)
    result["parse_evidence"] = {
        **result.get("parse_evidence", {}),
        "part_resolution": {"status": "unidentified", "selected_part": "generic"},
    }
    return result


def _merge_ocr_metadata(parsed: dict[str, Any], metadata: OcrMetadata) -> dict[str, Any]:
    """파서 결과에 OCR 출처와 신뢰도 정보를 덧붙인다."""

    result = dict(parsed)
    confidence = dict(result.get("confidence", {}))
    confidence["ocr"] = metadata.confidence
    result["confidence"] = confidence

    warnings = list(result.get("warnings", []))
    for warning in metadata.warnings:
        if warning not in warnings:
            warnings.append(warning)
    result["warnings"] = warnings
    if metadata.scoped_materials:
        result["parse_evidence"] = {
            **result.get("parse_evidence", {}),
            "scoped_materials": metadata.scoped_materials,
        }
        if "yarn_materials_are_not_primary_composition" not in warnings:
            warnings.append("yarn_materials_are_not_primary_composition")
    # 원문 전체는 raw_ocr_preview로 제한하고, 여기에는 재현에 필요한 메타데이터만 둔다.
    result["ocr"] = {
        "source": metadata.source,
        "candidate_count": metadata.candidate_count,
        "conflicting_parts": list(metadata.conflicting_parts),
        "unpaired_ratio_parts": list(metadata.unpaired_ratio_parts),
        "rejected_composition_parts": {
            part: list(reasons) for part, reasons in metadata.rejected_composition_parts.items()
        },
        "image_format": metadata.image_format,
        "width": metadata.width,
        "height": metadata.height,
        "attempt_failures": list(metadata.attempt_failures),
        "attempt_count": metadata.attempt_count,
        "external_call_count": metadata.external_call_count,
        "rpc_attempt_count": metadata.rpc_attempt_count,
        "retry_count": metadata.retry_count,
        "elapsed_ms": metadata.elapsed_ms,
        "attempts": [
            {
                "source": attempt.source,
                "outcome": attempt.outcome,
                "elapsed_ms": attempt.elapsed_ms,
                "external_call": attempt.external_call,
                "failure_code": attempt.failure_code,
                "retry_count": attempt.retry_count,
                "rpc_attempt_count": attempt.rpc_attempt_count,
            }
            for attempt in metadata.attempts
        ],
    }
    # OCR 메타데이터 조립까지 마친 최종 응답을 같은 계약으로 검증한다.
    return normalize_label_response(_with_part_uncertainty(result), api_version=API_VERSION)


def _first_composition_review(ocr_result: OcrResult) -> tuple[str, dict[str, Any]] | None:
    """Return one literal original-response option, never an automatic repair."""

    candidate = ocr_result.original_candidate
    if (candidate is None or candidate.source != "original" or candidate.layout_used
            or len(candidate.image_key) != 64
            or any(char not in "0123456789abcdef" for char in candidate.image_key)):
        return None
    parsed = _with_part_uncertainty(parse_label(candidate.text, confirmed_first_generic=True))
    if (parsed["status"] != "success" or parsed.get("selected_part") != "generic"
            or "confirmed_representative_selection:first_generic" not in parsed["warnings"]):
        return None
    # Bind the confirmation to this photo, OCR reading and interpretation.
    # The ID is a stale-selection guard, not authentication or authorization.
    identity = "\0".join(("first_generic/v1", candidate.image_key,
                           candidate.image_variant_key, candidate.text))
    option_id = "first_generic:" + hashlib.sha256(identity.encode("utf8")).hexdigest()
    return option_id, parsed


def _with_recapture_guidance(parsed: dict[str, Any]) -> dict[str, Any]:
    """Suggest a clearer composition photo only after completed OCR attempts.

    This describes the current OCR evidence, not whether the image could ever
    be recovered by another reader. Public failure fields remain unchanged.
    """

    evidence = parsed.get("parse_evidence", {})
    ocr = parsed.get("ocr", {})
    attempts = ocr.get("attempts", [])
    # A missing primary part may be incomplete or ambiguous; a conflict
    # needs review rather than being described as incomplete capture.
    if (parsed.get("status") != "failed"
            or parsed.get("error_code") not in {"composition_not_found", "incomplete_part_composition"}
            or evidence.get("review", {}).get("available")
            or ocr.get("conflicting_parts")
            or any(warning.rsplit(":", 1)[-1] in {
                "ambiguous_composition_candidates", "ambiguous_outer_compositions",
            } for warning in parsed.get("warnings", []))
            or ocr.get("attempt_failures")
            or not attempts
            or any(attempt.get("outcome") != "success" or attempt.get("failure_code")
                   for attempt in attempts)):
        return parsed
    has_composition_text = any(evidence.get("observed_materials", {}).values()) or any(
        evidence.get("observed_ratios", {}).values()
    )
    return {
        **parsed,
        "parse_evidence": {
            **evidence,
            "recapture": {
                "action": "retake_composition_region",
                "reason": "composition_incomplete" if has_composition_text else "composition_text_missing",
                "basis": "current_ocr",
            },
        },
    }


def get_ocr_review_options(ocr_result: OcrResult) -> list[dict[str, Any]]:
    """Show a composition for human review; this never confirms a scan.

    A consumer must display the material names and ratios and obtain explicit
    confirmation of those values, not just silently select the first option.
    """

    review = _first_composition_review(ocr_result)
    if review is None:
        return []
    option_id, parsed = review
    return [{
        "id": option_id,
        "selection": "first_generic",
        "source": "original",
        "selected_part": "generic",
        "materials": deepcopy(parsed["materials"]),
        "warnings": [warning for warning in parsed["warnings"]
                     if warning != "confirmed_representative_selection:first_generic"],
        "confirmation_required": True,
        "confirmation_scope": "materials_and_ratios",
    }]


@line_analysis_scope()
def analyze_ocr_result(
    ocr_result: OcrResult, *, confirmed_review_id: str | None = None,
) -> dict[str, Any]:
    """이미 OCR이 끝난 결과를 파싱한다. QA에서는 외부 OCR 호출 없이 이 함수를 쓴다."""

    if confirmed_review_id is not None and (
        type(confirmed_review_id) is not str or not confirmed_review_id
    ):
        raise ValueError("확인한 조성의 선택 ID는 비어 있지 않은 문자열이어야 합니다.")
    automatic = _merge_ocr_metadata(
        parse_label(
            ocr_result.text,
            conflicting_parts=ocr_result.metadata.conflicting_parts,
            unpaired_ratio_parts=ocr_result.metadata.unpaired_ratio_parts,
            rejected_composition_parts=ocr_result.metadata.rejected_composition_parts,
        ),
        ocr_result.metadata,
    )
    review = (_first_composition_review(ocr_result)
              if automatic["status"] == "failed" or confirmed_review_id is not None else None)
    if automatic["status"] == "failed" and review is not None:
        automatic["warnings"].append("manual_composition_review_required:first_generic")
        automatic["parse_evidence"]["review"] = {
            "available": True,
            "confirmed": False,
            "confirmation_required": True,
            "confirmation_scope": "materials_and_ratios",
            "selection": "first_generic",
            "source": "original",
            "selected_part": "generic",
            "option_id": review[0],
        }
    if confirmed_review_id is None:
        return _with_public_guidance(_with_recapture_guidance(automatic))

    if review is None or review[0] != confirmed_review_id:
        raise ValueError("선택 ID가 현재 OCR의 확인 후보와 일치하지 않습니다.")
    option_id, reviewed = review
    # Human confirmation applies to this displayed composition. It does not
    # resolve or erase any of the automatic candidate's rejection evidence.
    reviewed["ocr"] = deepcopy(automatic["ocr"])
    reviewed["confidence"]["ocr"] = automatic["confidence"]["ocr"]
    reviewed["confidence"]["parser"] = "medium"
    reviewed["warnings"].append("manual_composition_review_confirmed:first_generic")
    if automatic["status"] == "failed":
        reviewed["warnings"].append("automatic_composition_not_confirmed")
    reviewed["parse_evidence"]["review"] = {
        "confirmed": True,
        "confirmation_scope": "materials_and_ratios",
        "selection": "first_generic",
        "source": "original",
        "option_id": option_id,
        "automatic_status": automatic["status"],
        "automatic_error_code": automatic["error_code"],
        "automatic_ocr_source": automatic["ocr"]["source"],
        "automatic_warnings": list(automatic["warnings"]),
    }
    return normalize_label_response(_with_public_guidance(reviewed), api_version=API_VERSION)


@line_analysis_scope()
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


def analyze_label_text(
    text: str, *, confirmed_polyester_poly: bool = False,
    confirmed_first_generic: bool = False,
) -> dict[str, Any]:
    """Parse extracted text; explicit per-label review options never imply OCR confidence."""

    return normalize_label_response(_with_public_guidance(_with_part_uncertainty(parse_label(
        text, confirmed_polyester_poly=confirmed_polyester_poly,
        confirmed_first_generic=confirmed_first_generic,
    ))), api_version=API_VERSION)
