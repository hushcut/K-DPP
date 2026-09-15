"""고정 QA 이미지셋으로 OCR·소재 파서 결과를 재현 가능하게 측정하는 도구.

기본 동작은 OCR 캐시를 재사용한다. 따라서 파서 규칙을 수정한 뒤에는 외부
OCR 비용 없이 같은 원문 기준으로 결과를 비교할 수 있다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps.service.label_analysis import analyze_ocr_result
from apps.text.qa_comparison import compare_material_compositions
from apps.text.ocr_cache import (
    OcrCacheError,
    OcrTextCache,
)
from apps.text.ocr_text import OcrError, read_image_bytes, run_ocr_bytes
from apps.text.qa_dataset import (
    QaDatasetError,
    load_qa_answer_key,
    parse_answer_materials as parse_qa_answer_materials,
)


BASE_DIR = Path(__file__).resolve().parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


AnswerKeyError = QaDatasetError


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
    failure_category_counts: dict[str, int]


def csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def parse_answer_materials(
    row: dict[str, str],
    *,
    row_number: int,
) -> dict[str, float]:
    """Backward-compatible access to the shared QA annotation parser."""

    return parse_qa_answer_materials(row, row_number=row_number)


def load_answer_key(path: Path) -> dict[str, dict[str, Any]]:
    """Load canonical answers plus optional capture-condition metadata."""

    answers = load_qa_answer_key(path)
    return {
        file_name: {
            "_materials": answer.materials,
            "_original_materials": answer.original_materials,
            "include_in_accuracy": answer.include_in_accuracy,
            "split": answer.split or "",
            "source_group": answer.source_group or "",
            "capture_condition": answer.capture_condition or "",
            "label_layout": answer.label_layout or "",
        }
        for file_name, answer in answers.items()
    }


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
    """이미지 하나를 분석하고, 이번 결과가 OCR 캐시만 사용했는지 함께 반환한다."""

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


def compare_materials(
    answer: dict[str, float],
    predicted: dict[str, float],
    tolerance: float,
) -> tuple[str, str]:
    """정답과 예측의 소재 집합·혼용률을 비교해 사람이 읽을 실패 이유를 만든다."""

    if not predicted:
        return "failed", "no_predicted_materials"
    comparison = compare_material_compositions(
        answer,
        predicted,
        tolerance=tolerance,
    )
    return comparison.judgment, comparison.failure_reason


def classify_failure(
    *,
    result: dict[str, Any],
    exception: str,
    judgment: str,
    failure_reason: str,
) -> str:
    """Return one stable failure category for QA trend analysis."""

    if judgment == "not_compared":
        return "not_compared"
    if exception:
        return "ocr_or_pipeline_exception"
    if result.get("status") != "success":
        return str(result.get("error_code") or "parser_failed")
    if judgment == "success":
        return "success"
    if failure_reason == "no_predicted_materials":
        return "parser_returned_no_materials"
    if "missing=" in failure_reason and "extra=" in failure_reason:
        return "material_missing_and_extra"
    if "missing=" in failure_reason:
        return "material_missing"
    if "extra=" in failure_reason:
        return "material_extra"
    if "ratio_diff=" in failure_reason:
        return "ratio_mismatch"
    return "composition_mismatch"


def build_summary(
    rows: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
) -> QaSummary:
    """정확 일치와 소재 단위 precision/recall/F1을 함께 계산한다."""

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
        failure_category_counts=dict(
            sorted(
                Counter(
                    row["failure_category"]
                    for row in rows
                    if row["failure_category"] not in {"success", "not_compared"}
                ).items()
            )
        ),
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
        "--include-unanswered",
        action="store_true",
        help="Also run images that are not listed in the answer key.",
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
    args = parser.parse_args(sys.argv[1:])
    if args.tolerance < 0:
        raise ValueError("--tolerance은 0 이상이어야 합니다.")
    if args.offline and args.refresh_ocr_cache:
        raise ValueError("--offline과 --refresh-ocr-cache는 함께 사용할 수 없습니다.")

    image_dir = Path(args.image_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    cache_path = Path(args.ocr_cache).expanduser().resolve()
    cache = OcrTextCache(
        cache_path,
        reset_stale_cache=args.refresh_ocr_cache,
    )
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

    images_by_name: dict[str, list[Path]] = {}
    for image_path in images:
        images_by_name.setdefault(image_path.name, []).append(image_path)
    duplicate_answer_names = sorted(
        name
        for name, matching_paths in images_by_name.items()
        if name in answers and len(matching_paths) > 1
    )
    if duplicate_answer_names:
        examples = ", ".join(duplicate_answer_names[:3])
        raise AnswerKeyError(
            "정답 CSV의 file_name과 같은 이미지가 여러 경로에 있습니다. "
            "대상 이미지 폴더를 더 구체적으로 지정하세요: "
            f"{examples}"
        )

    if args.include_unanswered:
        selected_images = images
    else:
        # 기본값은 정답이 있는 이미지로 제한해, 폴더에 섞인 다른 이미지가
        # Google Vision 호출 비용과 QA 결과에 영향을 주지 않게 한다.
        selected_images = [
            images_by_name[name][0]
            for name in sorted(answers)
            if name in images_by_name
        ]
    if not selected_images:
        raise AnswerKeyError("정답 CSV에 해당하는 처리 가능 이미지가 없습니다.")

    rows: list[dict[str, Any]] = []
    cache_hit_count = 0
    cache_miss_count = 0
    for image_path in selected_images:
        answer_metadata = answers.get(image_path.name, {})
        answer = answer_metadata.get("_materials", {})
        include_in_accuracy = bool(answer_metadata.get("include_in_accuracy", True))
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
        if not answer:
            judgment, failure_reason = "not_compared", "answer_missing"
        elif not include_in_accuracy:
            judgment, failure_reason = "not_compared", "excluded_by_annotation"
        else:
            judgment, failure_reason = compare_materials(answer, predicted, args.tolerance)
        failure_category = classify_failure(
            result=result,
            exception=exception,
            judgment=judgment,
            failure_reason=failure_reason,
        )
        confidence = result.get("confidence", {})
        ocr = result.get("ocr", {})
        row = {
            "file_name": image_path.name,
            "qa_scope": "ocr_parser",
            "include_in_accuracy": include_in_accuracy,
            "status": result.get("status", "failed"),
            "error_code": result.get("error_code", ""),
            "judgment": judgment,
            "failure_reason": failure_reason,
            "failure_category": failure_category,
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
            "ocr_attempt_failures": json.dumps(
                ocr.get("attempt_failures", []),
                ensure_ascii=False,
            ),
            "ocr_attempt_count": ocr.get("attempt_count", 0),
            "ocr_external_call_count": ocr.get("external_call_count", 0),
            "ocr_elapsed_ms": ocr.get("elapsed_ms", 0),
            "ocr_attempts": json.dumps(
                ocr.get("attempts", []),
                ensure_ascii=False,
            ),
            "warnings": json.dumps(
                result.get("warnings", []),
                ensure_ascii=False,
            ),
            "raw_ocr_preview": result.get("raw_ocr_preview", ""),
            "exception": exception,
            "split": answer_metadata.get("split", ""),
            "source_group": answer_metadata.get("source_group", ""),
            "capture_condition": answer_metadata.get("capture_condition", ""),
            "label_layout": answer_metadata.get("label_layout", ""),
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
    print(
        "Selected images/available images: "
        f"{len(selected_images)}/{len(images)}"
    )
    if summary.exception_count:
        raise SystemExit(
            f"QA 배치 중 예상 밖 예외가 {summary.exception_count}건 발생했습니다."
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
    if summary.failure_category_counts:
        print("Failure categories: " + json.dumps(summary.failure_category_counts, ensure_ascii=False))
    if missing_answers:
        print(f"Warning: answers missing for {len(missing_answers)} images")
    if missing_images:
        print(f"Warning: images missing for {len(missing_images)} answers")


if __name__ == "__main__":
    main()
