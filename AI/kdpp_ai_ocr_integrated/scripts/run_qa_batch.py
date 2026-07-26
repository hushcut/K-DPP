from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.service.label_analysis import analyze_ocr_result
from apps.text.ocr_cache import (
    OcrCacheError,
    OcrTextCache,
)
from apps.text.ocr_text import OcrError, read_image_bytes, run_ocr_bytes

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class AnswerKeyError(ValueError):
    pass


@dataclass
class QaSummary:
    image_count: int
    answer_count: int
    compared_count: int
    parser_success_count: int
    exact_composition_count: int
    exact_composition_accuracy: float
    material_micro_precision: float
    material_micro_recall: float
    material_micro_f1: float
    matched_material_ratio_mae: float | None
    exception_count: int


def csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _parse_ratio(value: str, *, row_number: int) -> float:
    try:
        ratio = float(value.strip())
    except ValueError as exc:
        raise AnswerKeyError(
            f"{row_number}행에 숫자가 아닌 혼용률이 있습니다: {value!r}"
        ) from exc
    if not math.isfinite(ratio) or ratio <= 0 or ratio > 100:
        raise AnswerKeyError(
            f"{row_number}행 혼용률은 0 초과 100 이하여야 합니다: {ratio}"
        )
    return ratio


def parse_answer_materials(row: dict[str, str], *, row_number: int) -> dict[str, float]:
    direct = (row.get("answer_materials") or "").strip()
    if not direct:
        raise AnswerKeyError(f"{row_number}행 answer_materials가 비어 있습니다.")

    result: dict[str, float] = {}
    if ":" in direct:
        items = [item.strip() for item in direct.split(";") if item.strip()]
        for item in items:
            if ":" not in item:
                raise AnswerKeyError(
                    f"{row_number}행 소재:비율 형식이 올바르지 않습니다: {item!r}"
                )
            material, raw_ratio = item.split(":", 1)
            material = material.strip().lower()
            if not material or material in result:
                raise AnswerKeyError(
                    f"{row_number}행 소재명이 비었거나 중복되었습니다: {material!r}"
                )
            result[material] = _parse_ratio(raw_ratio, row_number=row_number)
    else:
        materials = [
            item.strip().lower()
            for item in direct.split(";")
            if item.strip()
        ]
        ratios = [
            item.strip()
            for item in (row.get("answer_ratios") or "").split(";")
            if item.strip()
        ]
        if len(materials) != len(ratios):
            raise AnswerKeyError(
                f"{row_number}행 소재 {len(materials)}개와 비율 "
                f"{len(ratios)}개의 개수가 다릅니다."
            )
        if len(set(materials)) != len(materials):
            raise AnswerKeyError(f"{row_number}행 소재명이 중복되었습니다.")
        result = {
            material: _parse_ratio(ratio, row_number=row_number)
            for material, ratio in zip(materials, ratios)
        }

    total = sum(result.values())
    if abs(total - 100.0) > 0.5:
        raise AnswerKeyError(
            f"{row_number}행 정답 혼용률 합계가 100이 아닙니다: {total:g}"
        )
    return result


def load_answer_key(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"정답지 CSV가 없습니다: {path}")

    answers: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"file_name", "answer_materials", "answer_ratios"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise AnswerKeyError(
                "정답지 필수 열이 없습니다: " + ", ".join(sorted(missing))
            )
        for row_number, row in enumerate(reader, start=2):
            file_name = (row.get("file_name") or "").strip()
            if not file_name:
                raise AnswerKeyError(f"{row_number}행 file_name이 비어 있습니다.")
            if file_name in answers:
                raise AnswerKeyError(f"중복 file_name입니다: {file_name}")
            answers[file_name] = {
                **row,
                "_materials": parse_answer_materials(
                    row,
                    row_number=row_number,
                ),
            }
    return answers


def image_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise FileNotFoundError(f"이미지 폴더가 없습니다: {folder}")
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def analyze_label_image_cached(
    image_path: Path,
    *,
    cache: OcrTextCache,
    credential_path: str | None = None,
    refresh_cache: bool = False,
    offline: bool = False,
) -> tuple[dict[str, Any], bool]:
    content = read_image_bytes(image_path)
    writes_before = cache.write_count
    ocr_result = run_ocr_bytes(
        content,
        credential_path=credential_path,
        ocr_cache=cache,
        refresh_ocr_cache=refresh_cache,
        offline=offline,
        cache_label=image_path.name,
    )
    return analyze_ocr_result(ocr_result), cache.write_count == writes_before


def normalize_values(values: dict[str, float]) -> dict[str, float]:
    return {
        key.lower(): round(float(value), 4)
        for key, value in values.items()
        if value is not None
    }


def compare_materials(
    answer: dict[str, float],
    predicted: dict[str, float],
    tolerance: float,
) -> tuple[str, str]:
    answer = normalize_values(answer)
    predicted = normalize_values(predicted)

    if not predicted:
        return "failed", "no_predicted_materials"

    missing = sorted(set(answer) - set(predicted))
    extra = sorted(set(predicted) - set(answer))
    ratio_diffs = [
        f"{key}:{predicted[key] - answer[key]:+.1f}"
        for key in sorted(set(answer) & set(predicted))
        if abs(predicted[key] - answer[key]) > tolerance
    ]

    reasons = []
    if missing:
        reasons.append("missing=" + ";".join(missing))
    if extra:
        reasons.append("extra=" + ";".join(extra))
    if ratio_diffs:
        reasons.append("ratio_diff=" + ";".join(ratio_diffs))
    return ("failed", " | ".join(reasons)) if reasons else ("success", "")


def build_summary(
    rows: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
) -> QaSummary:
    compared = [row for row in rows if row["judgment"] in {"success", "failed"}]
    true_positive = false_positive = false_negative = 0
    ratio_errors: list[float] = []

    for row in compared:
        answer = json.loads(row["answer_materials"])
        predicted = json.loads(row["predicted_materials"])
        answer_keys = set(answer)
        predicted_keys = set(predicted)
        true_positive += len(answer_keys & predicted_keys)
        false_positive += len(predicted_keys - answer_keys)
        false_negative += len(answer_keys - predicted_keys)
        ratio_errors.extend(
            abs(float(predicted[key]) - float(answer[key]))
            for key in answer_keys & predicted_keys
        )

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    exact_count = sum(row["judgment"] == "success" for row in compared)
    return QaSummary(
        image_count=len(rows),
        answer_count=len(answers),
        compared_count=len(compared),
        parser_success_count=sum(
            row["status"] == "success" for row in rows
        ),
        exact_composition_count=exact_count,
        exact_composition_accuracy=(
            exact_count / len(compared) if compared else 0.0
        ),
        material_micro_precision=precision,
        material_micro_recall=recall,
        material_micro_f1=f1,
        matched_material_ratio_mae=(
            sum(ratio_errors) / len(ratio_errors)
            if ratio_errors
            else None
        ),
        exception_count=sum(bool(row["exception"]) for row in rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate K-DPP OCR material extraction against a CSV answer key."
    )
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--answer-key", required=True)
    parser.add_argument(
        "--credentials",
        default="",
        help=(
            "Google Vision service-account JSON. If omitted, "
            "GOOGLE_APPLICATION_CREDENTIALS is used."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "outputs" / "qa_batch_results.csv"),
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=3.0,
        help="Allowed percentage-point error for exact composition.",
    )
    parser.add_argument(
        "--strict-coverage",
        action="store_true",
        help="Fail before OCR if an image has no answer or an answer has no image.",
    )
    parser.add_argument(
        "--ocr-cache",
        default=str(BASE_DIR / "outputs" / "qa_ocr_cache.json"),
        help=(
            "Local raw OCR cache. It is reused by default so parser-only QA "
            "does not call Google Vision again."
        ),
    )
    parser.add_argument(
        "--refresh-ocr-cache",
        action="store_true",
        help="Call OCR again and replace cached entries.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use cached OCR only and never call Google Vision.",
    )
    args = parser.parse_args()
    if args.tolerance < 0:
        raise ValueError("--tolerance은 0 이상이어야 합니다.")
    if args.offline and args.refresh_ocr_cache:
        raise ValueError("--offline과 --refresh-ocr-cache는 함께 사용할 수 없습니다.")

    image_dir = Path(args.image_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    cache_path = Path(args.ocr_cache).expanduser().resolve()
    cache = OcrTextCache(cache_path)
    answers = load_answer_key(Path(args.answer_key).expanduser().resolve())
    images = image_files(image_dir)
    if not images:
        raise ValueError(f"처리할 JPG/PNG 이미지가 없습니다: {image_dir}")

    image_names = {path.name for path in images}
    missing_answers = sorted(image_names - set(answers))
    missing_images = sorted(set(answers) - image_names)
    if args.strict_coverage and (missing_answers or missing_images):
        raise AnswerKeyError(
            f"정답 누락 {len(missing_answers)}건, 이미지 누락 "
            f"{len(missing_images)}건"
        )

    rows: list[dict[str, Any]] = []
    cache_hit_count = 0
    cache_miss_count = 0
    for image_path in images:
        answer = answers.get(image_path.name, {}).get("_materials", {})
        result: dict[str, Any] = {
            "status": "failed",
            "error_code": "pipeline_exception",
            "materials": {},
        }
        exception = ""
        try:
            result, cache_hit = analyze_label_image_cached(
                image_path,
                cache=cache,
                credential_path=args.credentials or None,
                refresh_cache=args.refresh_ocr_cache,
                offline=args.offline,
            )
            if cache_hit:
                cache_hit_count += 1
            else:
                cache_miss_count += 1
        except OcrCacheError:
            raise
        except OcrError as exc:
            result["error_code"] = type(exc).__name__
            result["message"] = str(exc)
            exception = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            exception = f"{type(exc).__name__}: {exc}"

        predicted = result.get("materials", {})
        judgment, failure_reason = (
            compare_materials(answer, predicted, args.tolerance)
            if answer
            else ("not_compared", "answer_missing")
        )
        confidence = result.get("confidence", {})
        ocr = result.get("ocr", {})
        row = {
            "file_name": image_path.name,
            "status": result.get("status", "failed"),
            "error_code": result.get("error_code", ""),
            "judgment": judgment,
            "failure_reason": failure_reason,
            "answer_materials": json.dumps(
                answer,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "predicted_materials": json.dumps(
                predicted,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "materials_korean": result.get("materials_korean", ""),
            "selected_part": result.get("selected_part", ""),
            "parser_confidence": confidence.get("parser", ""),
            "ocr_confidence": confidence.get("ocr", ""),
            "ocr_source": ocr.get("source", ""),
            "warnings": json.dumps(
                result.get("warnings", []),
                ensure_ascii=False,
            ),
            "raw_ocr_preview": result.get("raw_ocr_preview", ""),
            "exception": exception,
        }
        rows.append({key: csv_safe(value) for key, value in row.items()})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = build_summary(rows, answers)
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved: {output_path}")
    print(f"Summary: {summary_path}")
    print(f"OCR cache: {cache_path}")
    print(
        "OCR cache hits/misses/writes: "
        f"{cache.hit_count}/{cache.miss_count}/{cache.write_count}"
    )
    print(
        "Fully cached/API-backed images: "
        f"{cache_hit_count}/{cache_miss_count}"
    )
    print(f"Images: {summary.image_count}")
    print(
        "Exact composition accuracy: "
        f"{summary.exact_composition_accuracy * 100:.1f}% "
        f"({summary.exact_composition_count}/{summary.compared_count})"
    )
    print(
        "Material micro P/R/F1: "
        f"{summary.material_micro_precision:.3f}/"
        f"{summary.material_micro_recall:.3f}/"
        f"{summary.material_micro_f1:.3f}"
    )
    if missing_answers:
        print(f"Warning: answers missing for {len(missing_answers)} images")
    if missing_images:
        print(f"Warning: images missing for {len(missing_images)} answers")


if __name__ == "__main__":
    main()
