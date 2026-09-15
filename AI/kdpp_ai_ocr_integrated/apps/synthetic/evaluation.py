"""Parser-only evaluation for deterministic synthetic label manifests."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from apps.text.parse_label import parse_label
from apps.text.qa_comparison import compare_material_compositions
from apps.text.qa_dataset import QaDatasetError, parse_answer_materials


EVALUATION_TYPE = "synthetic_parser_only"
MANIFEST_REQUIRED_COLUMNS = frozenset(
    {
        "file_name",
        "source_group",
        "language",
        "condition",
        "answer_materials",
        "answer_ratios",
        "original_text",
    }
)
RESULT_COLUMNS = (
    "file_name",
    "source_group",
    "language",
    "condition",
    "layout",
    "theme",
    "jpeg_quality",
    "parse_status",
    "parser_source",
    "answer_materials",
    "predicted_materials",
    "judgment",
    "failure_category",
    "failure_reason",
)
GROUP_RESULT_COLUMNS = (
    "source_group",
    "image_count",
    "exact_composition_count",
    "exact_composition_accuracy",
    "group_judgment",
)


class SyntheticEvaluationError(ValueError):
    """A synthetic manifest cannot be evaluated under the parser-only contract."""


def _load_manifest(path: str | Path) -> list[dict[str, str]]:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"합성 manifest CSV가 없습니다: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = sorted(MANIFEST_REQUIRED_COLUMNS - columns)
        if missing:
            raise SyntheticEvaluationError(
                "합성 manifest 필수 열이 없습니다: " + ", ".join(missing)
            )
        rows = list(reader)

    if not rows:
        raise SyntheticEvaluationError("합성 manifest에 평가할 행이 없습니다.")
    return rows


def _materials_json(materials: dict[str, float | int]) -> str:
    return json.dumps(materials, ensure_ascii=False, sort_keys=True)


def _rate(success_count: int, total_count: int) -> float:
    return round(success_count / total_count, 4) if total_count else 0.0


def _aggregate_by(
    results: list[dict[str, str]],
    column: str,
) -> dict[str, dict[str, int | float]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for result in results:
        grouped[result[column]].append(result)
    return {
        key: {
            "image_count": len(group),
            "exact_composition_count": sum(
                row["judgment"] == "success" for row in group
            ),
            "exact_composition_accuracy": _rate(
                sum(row["judgment"] == "success" for row in group),
                len(group),
            ),
        }
        for key, group in sorted(grouped.items())
    }


def evaluate_manifest(
    manifest_path: str | Path,
    *,
    tolerance: float = 0.0,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """Evaluate manifest text with the parser, without image OCR or API calls."""

    if tolerance < 0:
        raise ValueError("혼용률 허용 오차는 0 이상이어야 합니다.")

    results: list[dict[str, str]] = []
    for row_number, row in enumerate(_load_manifest(manifest_path), start=2):
        try:
            expected = parse_answer_materials(row, row_number=row_number)
        except QaDatasetError as exc:
            raise SyntheticEvaluationError(str(exc)) from exc

        parsed = parse_label(row["original_text"])
        predicted = parsed.get("materials", {})
        if parsed["status"] != "success":
            judgment = "failed"
            failure_category = str(parsed.get("error_code") or "parser_failed")
            failure_reason = failure_category
        else:
            comparison = compare_material_compositions(
                expected,
                predicted,
                tolerance=tolerance,
            )
            judgment = comparison.judgment
            failure_category = comparison.failure_category
            failure_reason = comparison.failure_reason

        results.append(
            {
                "file_name": row["file_name"],
                "source_group": row["source_group"],
                "language": row["language"],
                "condition": row["condition"],
                "layout": row.get("layout", ""),
                "theme": row.get("theme", ""),
                "jpeg_quality": row.get("jpeg_quality", ""),
                "parse_status": str(parsed["status"]),
                "parser_source": str(
                    parsed.get("parse_evidence", {}).get("source", "")
                ),
                "answer_materials": _materials_json(expected),
                "predicted_materials": _materials_json(predicted),
                "judgment": judgment,
                "failure_category": failure_category,
                "failure_reason": failure_reason,
            }
        )

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for result in results:
        grouped[result["source_group"]].append(result)
    group_results = [
        {
            "source_group": group_name,
            "image_count": str(len(group)),
            "exact_composition_count": str(
                sum(row["judgment"] == "success" for row in group)
            ),
            "exact_composition_accuracy": str(
                _rate(sum(row["judgment"] == "success" for row in group), len(group))
            ),
            "group_judgment": (
                "success" if all(row["judgment"] == "success" for row in group) else "failed"
            ),
        }
        for group_name, group in sorted(grouped.items())
    ]
    exact_count = sum(row["judgment"] == "success" for row in results)
    group_success_count = sum(
        row["group_judgment"] == "success" for row in group_results
    )
    summary: dict[str, Any] = {
        "evaluation_type": EVALUATION_TYPE,
        "ocr_called": False,
        "image_count": len(results),
        "image_exact_composition_count": exact_count,
        "image_exact_composition_accuracy": _rate(exact_count, len(results)),
        "source_group_count": len(group_results),
        "source_group_all_variants_count": group_success_count,
        "source_group_all_variants_accuracy": _rate(
            group_success_count,
            len(group_results),
        ),
        "by_language": _aggregate_by(results, "language"),
        "by_condition": _aggregate_by(results, "condition"),
    }
    if all(result["layout"] for result in results):
        summary["by_layout"] = _aggregate_by(results, "layout")
    if all(result["theme"] for result in results):
        summary["by_theme"] = _aggregate_by(results, "theme")
    return results, group_results, summary


def write_evaluation(
    output_dir: str | Path,
    results: list[dict[str, str]],
    group_results: list[dict[str, str]],
    summary: dict[str, Any],
) -> Path:
    """Write synthetic-only results without overwriting a prior evaluation."""

    destination = Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"합성 평가 출력 폴더가 비어 있지 않습니다: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    with (destination / "image_results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    with (destination / "source_group_results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=GROUP_RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(group_results)
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination
