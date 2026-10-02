"""OCR 텍스트 후보를 파서 결과로 비교하는 순수 규칙 모음."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from apps.text.composition_candidates import equivalent_composition


@dataclass(frozen=True)
class OcrCandidate:
    """One OCR text candidate scored without provider-specific state."""

    source: str
    text: str
    materials: dict[str, float | int]
    selected_part: str
    parser_status: str
    parser_confidence: str
    score: tuple[int, int, int, int, float, int, int, int]
    layout_used: bool = False
    parts: dict[str, dict[str, float | int]] = field(default_factory=dict)
    conflicting_parts: tuple[str, ...] = ()
    observed_ratios: dict[str, list[float]] = field(default_factory=dict)
    unpaired_ratio_parts: tuple[str, ...] = ()


def find_conflicting_parts(candidates: list[OcrCandidate]) -> tuple[str, ...]:
    """후보 간 상충과 개별 파서가 이미 확인한 조성 충돌을 함께 보존한다."""

    compositions: dict[str, tuple[tuple[str, float | int], ...]] = {}
    conflicts: set[str] = set()
    for candidate in candidates:
        conflicts.update(candidate.conflicting_parts)
        if candidate.parser_status != "success":
            continue
        for part, materials in candidate.parts.items():
            composition = equivalent_composition(materials)
            previous = compositions.setdefault(part, composition)
            if previous != composition:
                conflicts.add(part)
    return tuple(sorted(conflicts))


def find_unpaired_ratio_parts(candidates: list[OcrCandidate]) -> tuple[str, ...]:
    """잔여 비율은 다른 후보가 같은 값과 개수를 모두 연결한 경우에만 해소한다."""

    unresolved: set[str] = set()
    for candidate in candidates:
        for part in candidate.unpaired_ratio_parts:
            required = Counter(
                ratio
                for key, ratios in candidate.observed_ratios.items()
                if part == "generic" or key == part
                for ratio in ratios
            )
            resolved = False
            for alternative in candidates:
                if alternative.parser_status != "success":
                    continue
                # 부위명이 없는 원문의 숫자는 좌표 복원으로 여러 부위에 연결될 수 있다.
                parts = alternative.parts.keys() if part == "generic" else (part,)
                available = Counter(
                    ratio
                    for key in parts if key in alternative.parts
                    for ratio in alternative.observed_ratios.get(key, [])
                )
                if required and available >= required:
                    resolved = True
                    break
            if not resolved:
                unresolved.add(part)
    return tuple(sorted(unresolved))


def score_candidate(
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
    """파서 성공 여부를 최우선으로 OCR 후보를 정렬할 점수를 만든다."""

    total = (
        ratio_total_before_normalization
        if ratio_total_before_normalization is not None
        else sum(float(value) for value in materials.values())
        if materials
        else 0.0
    )
    confidence_rank = {"low": 0, "medium": 1, "high": 2}.get(parser_confidence, 0)
    part_rank = {
        "outer": 7,
        "generic": 6,
        "lining": 5,
        "filling": 4,
        "pocket": 3,
        "rib": 2,
        "sleeve": 1,
        "color_block": 0,
    }.get(selected_part, 0)
    explicit_percent_count = len(re.findall(r"\d{1,3}(?:\.\d+)?\s*[%％]", text))
    source_priority = 1 if source == "original" else 0

    return (
        1 if parser_status == "success" else 0,
        part_rank,
        len(materials),
        confidence_rank,
        -abs(100.0 - total) if materials else -100.0,
        -warning_count,
        min(explicit_percent_count, 4),
        source_priority,
    )


def build_candidate(
    source: str,
    text: str,
    *,
    parse_candidate: Callable[[str], dict[str, Any]],
    layout_used: bool = False,
) -> OcrCandidate:
    """Parse one OCR text and retain only the evidence required for ranking."""

    parsed = parse_candidate(text)
    materials = parsed.get("materials", {})
    selected_part = parsed.get("selected_part", "")
    parser_status = parsed.get("status", "failed")
    parser_confidence = parsed.get("confidence", {}).get("parser", "low")
    ratio_total = parsed.get("parse_evidence", {}).get(
        "ratio_total_before_normalization"
    )
    parser_warnings = parsed.get("warnings", [])
    evidence = parsed.get("parse_evidence", {})
    return OcrCandidate(
        source=source,
        text=text,
        materials=materials,
        selected_part=selected_part,
        parser_status=parser_status,
        parser_confidence=parser_confidence,
        score=score_candidate(
            text,
            materials,
            selected_part,
            parser_status,
            parser_confidence,
            source,
            ratio_total_before_normalization=ratio_total,
            warning_count=len(parser_warnings),
        ),
        layout_used=layout_used,
        parts=parsed.get("parts", {}),
        conflicting_parts=tuple(sorted({
            warning.split(":", 1)[0]
            for warning in parser_warnings
            if warning.endswith(":ambiguous_composition_candidates")
        })),
        observed_ratios=evidence.get("observed_ratios", {}),
        unpaired_ratio_parts=tuple(evidence.get("unpaired_ratio_parts", [])),
    )
