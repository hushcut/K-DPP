"""Run batch QA tests against the K-DPP /api/scan endpoint.

This script sends each image listed in an answer-key CSV to the backend,
compares the returned materials with the human-written answer, and writes a
CSV result file for QA review.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AI_ROOT = REPOSITORY_ROOT / "AI" / "kdpp_ai_ocr_integrated"
if str(AI_ROOT) not in sys.path:
    # QA는 AI 정답지 계약을 재사용하되, API 호출 책임은 이 파일에 남긴다.
    sys.path.insert(0, str(AI_ROOT))

from apps.text.qa_comparison import (
    QaComparisonError,
    compare_material_compositions,
    normalize_material_mapping,
)
from apps.text.qa_dataset import load_qa_answer_key


DEFAULT_API_URL = "http://127.0.0.1:8000/api/scan"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_TOLERANCE = 5.0


@dataclass
class AnswerCase:
    row: dict[str, str]
    case_id: str
    file_name: str
    original_materials: dict[str, float]
    normalized_materials: dict[str, float]
    case_type: str
    include_in_accuracy: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="K-DPP QA dataset batch runner",
    )
    parser.add_argument(
        "--answers",
        required=True,
        help="Path to answer_key.csv",
    )
    parser.add_argument(
        "--images",
        required=True,
        help="Directory containing QA image files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write qa_result.csv",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Scan API URL. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Request timeout seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"Allowed ratio error in percentage points. Default: {DEFAULT_TOLERANCE}",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Optional seconds to wait between requests.",
    )
    return parser.parse_args()


def format_materials(materials: dict[str, float]) -> str:
    if not materials:
        return ""

    return ";".join(
        f"{key}:{value:g}" for key, value in sorted(materials.items())
    )


def read_answer_cases(path: Path) -> list[AnswerCase]:
    canonical_answers = load_qa_answer_key(path)
    cases: list[AnswerCase] = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"id", "file_name", "answer_materials", "answer_ratios"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"answer CSV missing columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            case_id = (row.get("id") or "").strip()
            file_name = (row.get("file_name") or "").strip()
            if not case_id and not file_name:
                continue
            if not case_id or not file_name:
                raise ValueError(f"row {row_number}: id and file_name are required")

            answer = canonical_answers[file_name]

            cases.append(
                AnswerCase(
                    row=row,
                    case_id=case_id,
                    file_name=file_name,
                    original_materials=answer.original_materials,
                    normalized_materials=answer.materials,
                    case_type=(row.get("case_type") or "일반 라벨").strip(),
                    include_in_accuracy=answer.include_in_accuracy,
                )
            )

    return cases


def build_multipart_body(image_path: Path) -> tuple[bytes, str]:
    boundary = f"----KDPPOCRQA{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    image_bytes = image_path.read_bytes()

    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            'Content-Disposition: form-data; name="image"; '
            f'filename="{image_path.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        image_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]

    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def call_scan_api(api_url: str, image_path: Path, timeout: int) -> tuple[int, dict[str, Any], str]:
    body, content_type = build_multipart_body(image_path)
    req = request.Request(
        api_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "ngrok-skip-browser-warning": "true",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw), raw
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {"status": "error", "message": raw}
        return exc.code, decoded, raw


def parse_api_materials(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("materials")
    if not isinstance(raw, dict):
        return {}

    try:
        return normalize_material_mapping(raw, allow_unknown=True)
    except QaComparisonError:
        # API 응답이 계약을 위반해도 전체 QA를 중단하지 않고 실패 행으로 남긴다.
        return {}


def classify_result(
    answer: dict[str, float],
    actual: dict[str, float],
    status_code: int | None,
    error_message: str,
    tolerance: float,
) -> tuple[str, str, str]:
    if status_code is None:
        return "서버/API 실패", error_message or "request_failed", "server_or_api_failure"

    if status_code < 200 or status_code >= 300:
        if status_code == 422:
            return "OCR 실패", "AI 인식 실패 또는 소재/혼용률 추출 실패", "ocr_or_parser_failure"
        return "서버/API 실패", f"HTTP {status_code}: {error_message}", "server_or_api_failure"

    if not actual:
        return "OCR 실패", "AI 결과 소재 없음", "parser_returned_no_materials"

    comparison = compare_material_compositions(answer, actual, tolerance=tolerance)
    if comparison.judgment == "success":
        return "완전 성공", "없음", comparison.failure_category
    if comparison.missing or comparison.extra:
        return "소재 실패", comparison.failure_reason, comparison.failure_category
    return "소재 성공/비율 실패", comparison.failure_reason, comparison.failure_category


def extract_error_message(payload: dict[str, Any], raw: str) -> str:
    message = payload.get("message") or payload.get("detail") or payload.get("error")
    if isinstance(message, dict):
        return json.dumps(message, ensure_ascii=False)
    if message:
        return str(message)
    return raw[:300]


def build_result_row(
    case: AnswerCase,
    image_path: Path,
    api_url: str,
    timeout: int,
    tolerance: float,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    status_code: int | None = None
    payload: dict[str, Any] = {}
    raw_response = ""
    exception_text = ""

    try:
        status_code, payload, raw_response = call_scan_api(api_url, image_path, timeout)
    except Exception as exc:  # noqa: BLE001 - QA output should record all failures.
        exception_text = f"{type(exc).__name__}: {exc}"
        raw_response = traceback.format_exc(limit=2)

    elapsed = time.perf_counter() - started_at
    ai_materials = parse_api_materials(payload)
    error_message = exception_text or extract_error_message(payload, raw_response)
    if case.include_in_accuracy:
        judgment, failure_reason, failure_category = classify_result(
            answer=case.normalized_materials,
            actual=ai_materials,
            status_code=status_code,
            error_message=error_message,
            tolerance=tolerance,
        )
    else:
        judgment = "정확도 제외"
        failure_reason = "복합/부위별 라벨 또는 현재 일반 정확도 계산 대상 제외"
        failure_category = "not_compared"

    row = {
        "id": case.case_id,
        "qa_scope": "integration_api",
        "file_name": case.file_name,
        "case_type": case.case_type,
        "include_in_accuracy": "TRUE" if case.include_in_accuracy else "FALSE",
        "shooting_pose": case.row.get("shooting_pose", ""),
        "lighting": case.row.get("lighting", ""),
        "resolution": case.row.get("resolution", ""),
        "label_language": case.row.get("label_language", ""),
        "label_condition": case.row.get("label_condition", ""),
        "notation_type": case.row.get("notation_type", ""),
        "answer_materials": format_materials(case.original_materials),
        "normalized_answer_materials": format_materials(case.normalized_materials),
        "ai_materials": format_materials(ai_materials),
        "judgment": judgment,
        "failure_category": failure_category,
        "http_status": status_code if status_code is not None else "",
        "failure_reason": failure_reason,
        "error_message": error_message,
        "carbon_footprint": payload.get("carbon_footprint", ""),
        "care_instruction": payload.get("care_instruction", ""),
        "raw_response": raw_response,
        "elapsed_seconds": f"{elapsed:.2f}",
        "memo": case.row.get("memo", ""),
    }
    return row


def write_results(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "qa_scope",
        "file_name",
        "case_type",
        "include_in_accuracy",
        "shooting_pose",
        "lighting",
        "resolution",
        "label_language",
        "label_condition",
        "notation_type",
        "answer_materials",
        "normalized_answer_materials",
        "ai_materials",
        "judgment",
        "failure_category",
        "http_status",
        "failure_reason",
        "error_message",
        "carbon_footprint",
        "care_instruction",
        "raw_response",
        "elapsed_seconds",
        "memo",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    included_rows = [
        row for row in rows if str(row.get("include_in_accuracy", "")).upper() == "TRUE"
    ]
    counts: dict[str, int] = {}
    for row in included_rows:
        judgment = str(row["judgment"])
        counts[judgment] = counts.get(judgment, 0) + 1
    excluded = total - len(included_rows)

    print("\n=== QA batch summary ===")
    print(f"Total: {total}")
    print(f"Included in accuracy: {len(included_rows)}")
    print(f"Excluded from accuracy: {excluded}")
    for judgment, count in sorted(counts.items()):
        ratio = (count / len(included_rows) * 100) if included_rows else 0.0
        print(f"- {judgment}: {count} ({ratio:.1f}%)")


def main() -> int:
    args = parse_args()
    answers_path = Path(args.answers)
    images_dir = Path(args.images)
    output_path = Path(args.output)

    cases = read_answer_cases(answers_path)
    if not cases:
        print("No answer cases found.", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    print(f"API URL: {args.api_url}")
    print(f"Cases: {len(cases)}")

    for index, case in enumerate(cases, start=1):
        image_path = images_dir / case.file_name
        print(f"[{index}/{len(cases)}] {case.case_id} {case.file_name}")

        if not image_path.exists():
            rows.append(
                {
                    "id": case.case_id,
                    "qa_scope": "integration_api",
                    "file_name": case.file_name,
                    "case_type": case.case_type,
                    "include_in_accuracy": "TRUE" if case.include_in_accuracy else "FALSE",
                    "shooting_pose": case.row.get("shooting_pose", ""),
                    "lighting": case.row.get("lighting", ""),
                    "resolution": case.row.get("resolution", ""),
                    "label_language": case.row.get("label_language", ""),
                    "label_condition": case.row.get("label_condition", ""),
                    "notation_type": case.row.get("notation_type", ""),
                    "answer_materials": format_materials(case.original_materials),
                    "normalized_answer_materials": format_materials(case.normalized_materials),
                    "ai_materials": "",
                    "judgment": "서버/API 실패",
                    "failure_category": "server_or_api_failure",
                    "http_status": "",
                    "failure_reason": "이미지 파일 없음",
                    "error_message": str(image_path),
                    "carbon_footprint": "",
                    "care_instruction": "",
                    "raw_response": "",
                    "elapsed_seconds": "",
                    "memo": case.row.get("memo", ""),
                }
            )
            continue

        rows.append(
            build_result_row(
                case=case,
                image_path=image_path,
                api_url=args.api_url,
                timeout=args.timeout,
                tolerance=args.tolerance,
            )
        )

        if args.sleep > 0:
            time.sleep(args.sleep)

    write_results(output_path, rows)
    print_summary(rows)
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
