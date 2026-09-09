"""OCR QA 정답지의 형식 검증과 데이터 품질 감사.

정답 CSV는 `file_name`, `answer_materials`, `answer_ratios`를 필수로 하며,
선택 메타데이터로 split·촬영 조건·원본 그룹을 기록한다. 이 정보는 평가
재현성과 train/valid/test 누수 확인에 사용한다.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.text.qa_comparison import QaComparisonError, canonical_material_name
from apps.text.parse_label import normalize_percentages
from apps.text.rules import MATERIAL_ALIASES

# 이 세 열만으로도 정답 구성비 비교는 가능하다.
QA_REQUIRED_COLUMNS = frozenset({"file_name", "answer_materials", "answer_ratios"})
# 데이터 품질 감사에서 빠짐을 보고할 핵심 메타데이터다. 통합 QA 전용 열은
# 선택적으로 읽되, 이 네 열이 없다는 이유만으로 정답지를 부적합 처리하지 않는다.
QA_OPTIONAL_COLUMNS = frozenset(
    {"split", "source_group", "capture_condition", "label_layout"}
)
QA_SPLITS = frozenset({"train", "valid", "test"})
CANONICAL_MATERIALS = frozenset(MATERIAL_ALIASES)


class QaDatasetError(ValueError):
    """The QA answer key is incomplete or violates the dataset contract."""


@dataclass(frozen=True)
class QaAnswer:
    file_name: str
    materials: dict[str, float]
    original_materials: dict[str, float]
    include_in_accuracy: bool
    split: str | None
    source_group: str | None
    capture_condition: str | None
    label_layout: str | None


@dataclass(frozen=True)
class QaDatasetAudit:
    answer_count: int
    material_sample_counts: dict[str, int]
    label_cardinality_counts: dict[int, int]
    split_counts: dict[str, int]
    condition_counts: dict[str, int]
    missing_optional_columns: tuple[str, ...]
    missing_metadata_counts: dict[str, int]
    source_group_split_leaks: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_count": self.answer_count,
            "material_sample_counts": dict(sorted(self.material_sample_counts.items())),
            "label_cardinality_counts": {
                str(cardinality): count
                for cardinality, count in sorted(self.label_cardinality_counts.items())
            },
            "split_counts": dict(sorted(self.split_counts.items())),
            "capture_condition_counts": dict(sorted(self.condition_counts.items())),
            "missing_optional_columns": list(self.missing_optional_columns),
            "missing_metadata_counts": dict(sorted(self.missing_metadata_counts.items())),
            "source_group_split_leaks": {
                group: list(splits)
                for group, splits in sorted(self.source_group_split_leaks.items())
            },
        }


def _parse_ratio(value: str, *, row_number: int) -> float:
    try:
        ratio = float(value.strip())
    except ValueError as exc:
        raise QaDatasetError(
            f"{row_number}행에 숫자가 아닌 혼용률이 있습니다: {value!r}"
        ) from exc
    if not math.isfinite(ratio) or not 0 < ratio <= 100:
        raise QaDatasetError(
            f"{row_number}행 혼용률은 0 초과 100 이하여야 합니다: {ratio}"
        )
    return ratio


def _canonical_material(value: str, *, row_number: int) -> str:
    try:
        return canonical_material_name(value, allow_unknown=False)
    except QaComparisonError as exc:
        supported = ", ".join(sorted(CANONICAL_MATERIALS))
        raise QaDatasetError(
            f"{row_number}행의 소재명이 표준 키 또는 별칭이 아닙니다: {value!r}. "
            f"허용 키: {supported}"
        ) from exc


def _normalize_evaluation_materials(
    materials: dict[str, float],
    *,
    row_number: int,
) -> dict[str, float]:
    """Match the parser's 95~105% acceptance and 100% normalization policy."""

    normalized = normalize_percentages(materials)
    if not normalized:
        total = sum(materials.values())
        raise QaDatasetError(
            f"{row_number}행 정확도 비교용 혼용률 합계는 95~105 범위여야 합니다: {total:g}"
        )
    return {material: float(ratio) for material, ratio in normalized.items()}


def parse_answer_materials(
    row: dict[str, str],
    *,
    row_number: int,
) -> dict[str, float]:
    """정답지 한 행을 표준 소재 키와 혼용률 딕셔너리로 변환한다.

    `cotton;polyester` + `80;20` 또는 `cotton:80;polyester:20`을 지원한다.
    합계가 100에서 0.5 이상 벗어나면 비교 대상에서 제외하지 않고 오류로 막는다.
    """

    direct = (row.get("answer_materials") or "").strip()
    if not direct:
        raise QaDatasetError(f"{row_number}행 answer_materials가 비어 있습니다.")

    materials: dict[str, float] = {}
    if ":" in direct:
        items = [item.strip() for item in direct.split(";") if item.strip()]
        for item in items:
            if ":" not in item:
                raise QaDatasetError(
                    f"{row_number}행 소재:비율 형식이 올바르지 않습니다: {item!r}"
                )
            raw_material, raw_ratio = item.split(":", 1)
            material = _canonical_material(raw_material, row_number=row_number)
            if material in materials:
                raise QaDatasetError(f"{row_number}행 소재명이 중복되었습니다: {material}")
            materials[material] = _parse_ratio(raw_ratio, row_number=row_number)
    else:
        material_values = [
            _canonical_material(item, row_number=row_number)
            for item in direct.split(";")
            if item.strip()
        ]
        ratio_values = [
            item.strip()
            for item in (row.get("answer_ratios") or "").split(";")
            if item.strip()
        ]
        if len(material_values) != len(ratio_values):
            raise QaDatasetError(
                f"{row_number}행 소재 {len(material_values)}개와 비율 "
                f"{len(ratio_values)}개의 개수가 다릅니다."
            )
        if len(set(material_values)) != len(material_values):
            raise QaDatasetError(f"{row_number}행 소재명이 중복되었습니다.")
        materials = {
            material: _parse_ratio(ratio, row_number=row_number)
            for material, ratio in zip(material_values, ratio_values)
        }

    return _normalize_evaluation_materials(materials, row_number=row_number)


def _parse_annotation_materials(
    row: dict[str, str],
    *,
    materials_column: str,
    ratios_column: str,
    row_number: int,
    require_total: bool,
) -> dict[str, float]:
    """Parse one material/ratio column pair, optionally allowing multi-part totals."""

    materials_text = (row.get(materials_column) or "").strip()
    ratios_text = (row.get(ratios_column) or "").strip()
    # OCR 단위 QA에서 허용하던 `cotton:80;polyester:20` 축약형도 유지한다.
    if ":" in materials_text:
        if ratios_text:
            raise QaDatasetError(
                f"{row_number}행 소재:비율 축약형에는 {ratios_column}을 함께 쓰지 않습니다."
            )
        return parse_answer_materials(
            {"answer_materials": materials_text},
            row_number=row_number,
        )
    if not materials_text and not ratios_text:
        return {}
    if not materials_text or not ratios_text:
        raise QaDatasetError(
            f"{row_number}행 {materials_column}/{ratios_column} 중 하나가 비어 있습니다."
        )
    materials = [
        _canonical_material(item, row_number=row_number)
        for item in materials_text.split(";")
        if item.strip()
    ]
    ratios = [item.strip() for item in ratios_text.split(";") if item.strip()]
    if len(materials) != len(ratios):
        raise QaDatasetError(
            f"{row_number}행 소재 {len(materials)}개와 비율 {len(ratios)}개의 개수가 다릅니다."
        )
    if len(set(materials)) != len(materials):
        raise QaDatasetError(f"{row_number}행 소재명이 중복되었습니다.")
    parsed = {
        material: _parse_ratio(ratio, row_number=row_number)
        for material, ratio in zip(materials, ratios)
    }
    return (
        _normalize_evaluation_materials(parsed, row_number=row_number)
        if require_total
        else parsed
    )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().casefold()
    if normalized in {"true", "yes", "y", "1", "include", "포함", "예"}:
        return True
    if normalized in {"false", "no", "n", "0", "exclude", "제외", "아니오"}:
        return False
    raise QaDatasetError(f"include_in_accuracy 값이 올바르지 않습니다: {value!r}")


def _optional_value(row: dict[str, str], column: str) -> str | None:
    value = row.get(column)
    return value.strip() if value and value.strip() else None


def load_qa_answer_key(path: str | Path) -> dict[str, QaAnswer]:
    """Load a QA answer key and enforce its documented annotation contract."""

    answer_path = Path(path)
    if not answer_path.is_file():
        raise FileNotFoundError(f"정답지 CSV가 없습니다: {answer_path}")

    answers: dict[str, QaAnswer] = {}
    with answer_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = QA_REQUIRED_COLUMNS - columns
        if missing:
            raise QaDatasetError(
                "정답지 필수 열이 없습니다: " + ", ".join(sorted(missing))
            )

        has_split = "split" in columns
        for row_number, row in enumerate(reader, start=2):
            file_name = (row.get("file_name") or "").strip()
            if not file_name:
                raise QaDatasetError(f"{row_number}행 file_name이 비어 있습니다.")
            if file_name in answers:
                raise QaDatasetError(f"중복 file_name입니다: {file_name}")

            split = _optional_value(row, "split")
            if has_split and split not in QA_SPLITS:
                raise QaDatasetError(
                    f"{row_number}행 split은 train, valid, test 중 하나여야 합니다: {split!r}"
                )

            include_in_accuracy = _parse_bool(
                row.get("include_in_accuracy"),
                default=True,
            )
            original_materials = _parse_annotation_materials(
                row,
                materials_column="answer_materials",
                ratios_column="answer_ratios",
                row_number=row_number,
                require_total=False,
            )
            normalized_materials = _parse_annotation_materials(
                row,
                materials_column="normalized_materials",
                ratios_column="normalized_ratios",
                row_number=row_number,
                require_total=True,
            )
            if include_in_accuracy:
                materials = normalized_materials or _normalize_evaluation_materials(
                    original_materials,
                    row_number=row_number,
                )
            else:
                materials = normalized_materials or original_materials

            answers[file_name] = QaAnswer(
                file_name=file_name,
                materials=materials,
                original_materials=original_materials,
                include_in_accuracy=include_in_accuracy,
                split=split,
                source_group=_optional_value(row, "source_group"),
                capture_condition=_optional_value(row, "capture_condition"),
                label_layout=_optional_value(row, "label_layout"),
            )
    return answers


def audit_qa_answer_key(
    answers: dict[str, QaAnswer],
    *,
    columns: set[str] | None = None,
) -> QaDatasetAudit:
    """Summarize annotation coverage and detect group leakage across splits."""

    material_counts: Counter[str] = Counter()
    cardinality_counts: Counter[int] = Counter()
    split_counts: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()
    missing_metadata_counts: Counter[str] = Counter()
    source_group_splits: dict[str, set[str]] = {}

    for answer in answers.values():
        # 데이터 감사는 대표 소재로 축소하기 전의 원문 조성 기준으로 센다.
        material_counts.update(answer.original_materials.keys())
        cardinality_counts[len(answer.original_materials)] += 1
        if answer.split:
            split_counts[answer.split] += 1
        else:
            missing_metadata_counts["split"] += 1
        if answer.capture_condition:
            condition_counts[answer.capture_condition] += 1
        else:
            missing_metadata_counts["capture_condition"] += 1
        if not answer.label_layout:
            missing_metadata_counts["label_layout"] += 1
        if not answer.source_group:
            missing_metadata_counts["source_group"] += 1
        elif answer.split:
            # 같은 실물 라벨의 다른 사진이 split을 가로지르면 평가가 과대평가된다.
            source_group_splits.setdefault(answer.source_group, set()).add(answer.split)

    available_columns = columns or set()
    missing_columns = tuple(sorted(QA_OPTIONAL_COLUMNS - available_columns))
    leaks = {
        group: tuple(sorted(splits))
        for group, splits in source_group_splits.items()
        if len(splits) > 1
    }
    return QaDatasetAudit(
        answer_count=len(answers),
        material_sample_counts=dict(material_counts),
        label_cardinality_counts=dict(cardinality_counts),
        split_counts=dict(split_counts),
        condition_counts=dict(condition_counts),
        missing_optional_columns=missing_columns,
        missing_metadata_counts=dict(missing_metadata_counts),
        source_group_split_leaks=leaks,
    )


def answer_key_columns(path: str | Path) -> set[str]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return set(csv.DictReader(file).fieldnames or [])
