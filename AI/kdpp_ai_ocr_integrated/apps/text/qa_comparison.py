"""OCR QA 실행기가 공유하는 소재 정규화와 조성 비교 규칙.

이 모듈은 OCR/파서 단위 QA와 `/api/scan` 통합 QA가 같은 소재 별칭,
혼용률 허용 오차, 실패 코드를 사용하게 한다. 두 실행기의 측정 범위와
기본 허용 오차는 다를 수 있으므로, 여기서는 비교 규칙만 제공한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from apps.text.rules import MATERIAL_ALIASES


class QaComparisonError(ValueError):
    """A QA material value cannot be converted into the canonical contract."""


def _build_alias_index() -> dict[str, str]:
    """Build the one-way alias lookup from the parser's source-of-truth table."""

    aliases: dict[str, str] = {}
    for canonical, values in MATERIAL_ALIASES.items():
        for value in [canonical, *values]:
            key = value.strip().casefold()
            previous = aliases.setdefault(key, canonical)
            if previous != canonical:
                raise RuntimeError(f"Ambiguous QA material alias: {value!r}")
    return aliases


MATERIAL_ALIAS_INDEX = _build_alias_index()


def canonical_material_name(value: str, *, allow_unknown: bool = False) -> str:
    """Normalize a human or API material name to the parser's canonical key."""

    key = value.strip().casefold().replace("%", "")
    if not key:
        raise QaComparisonError("소재명이 비어 있습니다.")
    canonical = MATERIAL_ALIAS_INDEX.get(key)
    if canonical:
        return canonical
    if allow_unknown:
        return key
    raise QaComparisonError(f"지원하지 않는 QA 소재명입니다: {value!r}")


def normalize_material_mapping(
    values: Mapping[str, object],
    *,
    allow_unknown: bool = True,
) -> dict[str, float]:
    """Normalize mapping keys and aggregate aliases that resolve to one material."""

    normalized: dict[str, float] = {}
    for raw_material, raw_ratio in values.items():
        material = canonical_material_name(str(raw_material), allow_unknown=allow_unknown)
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError) as exc:
            raise QaComparisonError(
                f"{raw_material!r}의 혼용률이 숫자가 아닙니다: {raw_ratio!r}"
            ) from exc
        if not math.isfinite(ratio) or ratio < 0:
            raise QaComparisonError(
                f"{raw_material!r}의 혼용률이 유효하지 않습니다: {raw_ratio!r}"
            )
        normalized[material] = normalized.get(material, 0.0) + ratio
    return {material: round(ratio, 4) for material, ratio in normalized.items()}


@dataclass(frozen=True)
class MaterialComparison:
    """Machine-readable comparison detail, shared by both QA runners."""

    missing: tuple[str, ...]
    extra: tuple[str, ...]
    ratio_differences: dict[str, float]

    @property
    def judgment(self) -> str:
        return "success" if not (self.missing or self.extra or self.ratio_differences) else "failed"

    @property
    def failure_reason(self) -> str:
        if self.judgment == "success":
            return ""
        parts: list[str] = []
        if self.missing:
            parts.append("missing=" + ";".join(self.missing))
        if self.extra:
            parts.append("extra=" + ";".join(self.extra))
        if self.ratio_differences:
            parts.append(
                "ratio_diff="
                + ";".join(
                    f"{material}:{difference:+.1f}"
                    for material, difference in self.ratio_differences.items()
                )
            )
        return " | ".join(parts)

    @property
    def failure_category(self) -> str:
        if self.judgment == "success":
            return "success"
        if self.missing and self.extra:
            return "material_missing_and_extra"
        if self.missing:
            return "material_missing"
        if self.extra:
            return "material_extra"
        return "ratio_mismatch"


def compare_material_compositions(
    answer: Mapping[str, object],
    predicted: Mapping[str, object],
    *,
    tolerance: float,
) -> MaterialComparison:
    """Compare material membership and ratio errors using percentage points."""

    if tolerance < 0:
        raise QaComparisonError("혼용률 허용 오차는 0 이상이어야 합니다.")
    expected = normalize_material_mapping(answer, allow_unknown=False)
    actual = normalize_material_mapping(predicted, allow_unknown=True)
    missing = tuple(sorted(set(expected) - set(actual)))
    extra = tuple(sorted(set(actual) - set(expected)))
    ratio_differences = {
        material: round(actual[material] - expected[material], 4)
        for material in sorted(set(expected) & set(actual))
        if abs(actual[material] - expected[material]) > tolerance
    }
    return MaterialComparison(missing, extra, ratio_differences)
