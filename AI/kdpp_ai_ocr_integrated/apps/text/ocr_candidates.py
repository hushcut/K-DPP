"""OCR 텍스트 후보를 파서 결과로 비교하는 순수 규칙 모음."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from apps.text.composition_candidates import equivalent_composition
from apps.text.material_extraction import PART_PATTERNS, extract_materials, normalize_text
from apps.text.rules import EQUIVALENT_MATERIALS
from apps.text.ocr_layout import OcrWord


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
    observed_materials: dict[str, list[str]] = field(default_factory=dict)
    paired_material_ratios: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    rejected_composition_parts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    image_key: str = ""
    image_variant_key: str = ""
    image_words: tuple[OcrWord, ...] = ()
    image_region: tuple[float, ...] = ()
    parser_warnings: tuple[str, ...] = ()


def agreed_original_composition(candidates: list[OcrCandidate]) -> bool:
    """같은 응답의 완전한 원문·좌표 해석이면 중간 신뢰도만으로 재호출하지 않는다."""

    originals = [candidate for candidate in candidates if candidate.source == "original"]
    for raw in originals:
        if raw.layout_used or raw.parser_status != "success" or raw.parser_warnings:
            continue
        if not raw.image_key or not raw.image_variant_key or not raw.image_words or len(raw.image_region) != 4:
            continue
        for layout in originals:
            if (
                not layout.layout_used or layout.parser_status != "success" or layout.parser_warnings
                or raw.image_key != layout.image_key or raw.image_variant_key != layout.image_variant_key
                or raw.image_words != layout.image_words
                or raw.image_region != layout.image_region
                or raw.selected_part != layout.selected_part or raw.parts != layout.parts
            ):
                continue
            if (
                raw.observed_materials.keys() == layout.observed_materials.keys()
                and raw.observed_ratios.keys() == layout.observed_ratios.keys()
                and all(Counter(raw.observed_materials[part]) == Counter(layout.observed_materials[part])
                        for part in raw.observed_materials)
                and all(Counter(raw.observed_ratios[part]) == Counter(layout.observed_ratios[part])
                        for part in raw.observed_ratios)
            ):
                return True
    return False


def rotated_layout_has_same_tokens(text: str, layout_text: str, words: tuple[OcrWord, ...]) -> bool:
    """Vertical word baselines cannot validate a horizontal row reconstruction."""

    token_pattern = r"[^\W\d_]+|\d+|[^\w\s]"
    tokens = Counter(re.findall(token_pattern, normalize_text(text)))
    if (
        tokens != Counter(re.findall(token_pattern, normalize_text(layout_text)))
        or tokens != Counter(re.findall(token_pattern, normalize_text(" ".join(word.text for word in words))))
    ):
        return False
    anchors = [word for word in words if len(word.vertices) == 4
               and (extract_materials(word.text) or "%" in word.text)]
    if (
        len(anchors) < 2 or not any(extract_materials(word.text) for word in anchors)
        or not any("%" in word.text for word in anchors)
    ):
        return False
    vertical = sum(
        abs(word.vertices[1][1] - word.vertices[0][1]) > 1.7 * abs(word.vertices[1][0] - word.vertices[0][0])
        for word in anchors
    )
    return vertical / len(anchors) >= 0.8


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
                from apps.text.ocr_corrections import same_region_recovery

                resolved = any(same_region_recovery(candidate, alternative, part, candidates) for alternative in candidates)
            if not resolved:
                from apps.text.ocr_corrections import located_generic_rejection_parts

                located = located_generic_rejection_parts(candidate, candidates) if part == "generic" else ()
                unresolved.update(located or (part,))
    return tuple(sorted(unresolved))


def _is_plain_part_heading(text: str, part: str) -> bool:
    heading = normalize_text(text).strip(" :;()[]{}")
    return heading in {normalize_text(alias) for alias in PART_PATTERNS.get(part, [])}


def _can_resolve_duplicate_material_rows(
    candidate: OcrCandidate,
    part: str,
    required_materials: Counter[str],
    required_ratios: Counter[float],
    available_pairs: set[tuple[str, float | int]],
) -> bool:
    """명시 부위의 연속 소재 중복을 같은 부위의 확정 100% 후보로만 해소한다."""

    if (
        part == "generic"
        or len(required_materials) != 1
        or required_ratios != Counter({100.0: 1})
        or candidate.paired_material_ratios.get(part)
    ):
        return False
    material, count = next(iter(required_materials.items()))
    if count < 2 or available_pairs != {(material, 100)}:
        return False

    from apps.text.parse_label import build_line_infos

    infos = build_line_infos(candidate.text)
    markers = [i for i, info in enumerate(infos) if info.marker_part == part]
    positions = [i for i, info in enumerate(infos) if info.part == part and info.materials]
    if len(markers) != 1 or len(positions) != count:
        return False
    first, last = positions[0], positions[-1]
    marker = markers[0]
    if first != marker and not (
        first == marker + 1 and infos[marker].is_standalone_marker
        and _is_plain_part_heading(infos[marker].normalized, part)
    ):
        return False
    # 원단 제목·메타데이터·다른 소재가 끼면 별도 조성을 버린 것으로 볼 수 있다.
    if positions != list(range(first, last + 1)) or last + 1 >= len(infos):
        return False
    # 100% 뒤에 남은 소재·다른 원단 제목을 중복 복원으로 숨기지 않는다.
    # 별도 부위로 넘어가기 전의 블록은 중복 소재와 그 비율만으로 끝나야 한다.
    if [i for i, info in enumerate(infos) if info.part == part] != list(
        range(marker, last + 2)
    ):
        return False
    for position in positions:
        info = infos[position]
        if (
            tuple(EQUIVALENT_MATERIALS.get(value, value) for value in info.materials)
            != (material,)
            or info.numbers
            or info.explicit_percent
            or info.unresolved_materials
            or info.invalid_evidence
            or info.is_metadata
        ):
            return False
    ratio = infos[last + 1]
    return (
        ratio.part == part
        and ratio.marker_part is None
        and not ratio.materials
        and ratio.numbers == (100,)
        and ratio.explicit_percent
        and not ratio.unresolved_materials
        and not ratio.invalid_evidence
        and not ratio.is_metadata
    )


def _is_empty_layout_part_marker(candidate: OcrCandidate, part: str) -> bool:
    """레이아웃이 남긴 부위 제목만 다른 후보의 같은 부위 조성으로 복원한다."""

    if not candidate.layout_used or part == "generic":
        return False
    from apps.text.parse_label import build_line_infos

    infos = [info for info in build_line_infos(candidate.text) if info.part == part]
    return (
        len(infos) == 1
        and infos[0].marker_part == part
        and infos[0].is_standalone_marker
        and _is_plain_part_heading(infos[0].normalized, part)
        and not infos[0].unresolved_materials
        and not infos[0].invalid_evidence
        and not infos[0].is_metadata
    )


def find_rejected_composition_parts(
    candidates: list[OcrCandidate], *, selected_part: str,
) -> dict[str, tuple[str, ...]]:
    """소재·숫자 누락은 검증된 복원으로만 해소하고 미등록·오류 근거는 보존한다."""

    rejected: dict[str, set[str]] = {}
    for candidate in candidates:
        for part, reasons in candidate.rejected_composition_parts.items():
            from apps.text.ocr_corrections import same_region_recovery

            resolved = any(same_region_recovery(candidate, alternative, part, candidates) for alternative in candidates)
            if not resolved and set(reasons) == {"unpaired_material_rows"}:
                source_parts = (
                    candidate.observed_materials.keys() | candidate.observed_ratios.keys()
                    if part == "generic" else (part,)
                )
                required_materials = Counter(
                    EQUIVALENT_MATERIALS.get(material, material)
                    for key in source_parts
                    for material in candidate.observed_materials.get(key, [])
                )
                required_ratios = Counter(
                    ratio for key in source_parts
                    for ratio in candidate.observed_ratios.get(key, [])
                )
                required_pairs = {
                    (EQUIVALENT_MATERIALS.get(material, material), ratio)
                    for key in source_parts
                    for material, ratio in candidate.paired_material_ratios.get(key, [])
                }
                empty_layout_marker = (
                    not required_materials
                    and not required_ratios
                    and not required_pairs
                    and _is_empty_layout_part_marker(candidate, part)
                )
                for alternative in candidates:
                    if alternative.parser_status != "success":
                        continue
                    # A single outer block cannot supply a missing ratio from
                    # a source that explicitly distinguishes two outer fabrics.
                    if (
                        "outer_2" in (
                            candidate.observed_materials.keys()
                            | candidate.observed_ratios.keys()
                            | candidate.rejected_composition_parts.keys()
                        )
                        and "outer_2" not in alternative.parts
                    ):
                        continue
                    target_parts = alternative.parts.keys() if part == "generic" else (part,)
                    valid_parts = [key for key in target_parts if key in alternative.parts]
                    available_materials = Counter(
                        EQUIVALENT_MATERIALS.get(material, material)
                        for key in valid_parts
                        for material in alternative.observed_materials.get(key, [])
                    )
                    available_ratios = Counter(
                        ratio for key in valid_parts
                        for ratio in alternative.observed_ratios.get(key, [])
                    )
                    available_pairs = {
                        pair for key in valid_parts
                        for pair in equivalent_composition(alternative.parts[key])
                    }
                    materials_resolved = available_materials >= required_materials
                    if not materials_resolved:
                        materials_resolved = _can_resolve_duplicate_material_rows(
                            candidate, part, required_materials, required_ratios, available_pairs,
                        )
                    # A complete explicit representative may coexist with
                    # additional fibers in a lower part (e.g. a lining). They
                    # cannot provide a missing name in the representative.
                    from apps.text.parse_label import PART_PRIORITY

                    new_material_parts = {
                        key for key in valid_parts
                        if any(EQUIVALENT_MATERIALS.get(material, material) not in required_materials
                               for material in alternative.observed_materials.get(key, []))
                    }
                    lower_parts_only = (
                        selected_part != "generic" and selected_part in PART_PRIORITY
                        and selected_part in alternative.parts
                        and set(equivalent_composition(alternative.parts[selected_part])) <= required_pairs
                        and new_material_parts <= set(PART_PRIORITY[PART_PRIORITY.index(selected_part) + 1:])
                    )
                    if (
                        (
                            required_materials or required_ratios
                            or (empty_layout_marker and available_pairs)
                        )
                        and materials_resolved
                        # Counts can restore known rows, never supply an unread
                        # fiber name. Such a repair requires coordinate proof.
                        and (empty_layout_marker or (
                            (available_materials.keys() <= required_materials.keys() or lower_parts_only)
                            and sum(required_ratios.values()) <= sum(required_materials.values())
                        ))
                        and available_ratios >= required_ratios
                        and required_pairs <= available_pairs
                    ):
                        resolved = True
                        break
            if not resolved:
                from apps.text.ocr_corrections import located_generic_rejection_parts

                located = located_generic_rejection_parts(candidate, candidates) if part == "generic" else ()
                for affected in located or (part,):
                    rejected.setdefault(affected, set()).update(reasons)
                # An isolated second-shell heading is still an unresolved outer
                # boundary; another candidate's unnumbered shell cannot erase it.
                if part == "outer_2" and selected_part == "outer" and "outer" not in candidate.observed_materials:
                    rejected.setdefault("outer", set()).update(reasons)
    # 부위 없는 거절 근거를 OUTER로 숨기지 않는다. 명시된 하위 부위는
    # 별도 조성으로 선택할 수 있으며 generic 거절 근거는 그대로 남긴다.
    if "generic" in rejected and selected_part in {"outer", "generic"}:
        rejected.setdefault(selected_part, set()).update(rejected["generic"])
    return {part: tuple(sorted(reasons)) for part, reasons in sorted(rejected.items())}


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
        "outer": 8,
        "generic": 7,
        "outer_2": 6,
        "lining": 5,
        "filling": 4,
        "pocket": 3,
        "rib": 2,
        "sleeve": 1,
        "color_block": 0,
        "embroidery_yarn": -1,
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
        observed_materials=evidence.get("observed_materials", {}),
        paired_material_ratios={
            part: [(material, ratio) for material, ratio in pairs]
            for part, pairs in evidence.get("paired_material_ratios", {}).items()
        },
        rejected_composition_parts={
            part: tuple(reasons)
            for part, reasons in evidence.get("rejected_composition_parts", {}).items()
        },
        parser_warnings=tuple(parser_warnings),
    )
