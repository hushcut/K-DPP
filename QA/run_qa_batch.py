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


def normalize_material_name(value: str) -> str:
    aliases = {
        "면": "cotton",
        "코튼": "cotton",
        "cotton": "cotton",
        "폴리에스터": "polyester",
        "폴리": "polyester",
        "poly": "polyester",
        "polyester": "polyester",
        "폴리우레탄": "polyurethane",
        "pu": "polyurethane",
        "polyurethane": "polyurethane",
        "스판": "spandex",
        "스판덱스": "spandex",
        "spandex": "spandex",
        "나일론": "nylon",
        "nylon": "nylon",
        "레이온": "rayon",
        "rayon": "rayon",
        "울": "wool",
        "모": "wool",
        "wool": "wool",
        "린넨": "linen",
        "linen": "linen",
        "마": "linen",
        "비스코스": "viscose",
        "viscose": "viscose",
        "실크": "silk",
        "silk": "silk",
        "모달": "modal",
        "modal": "modal",
        "아크릴": "acrylic",
        "acrylic": "acrylic",
        "arylic": "acrylic",
        "캐시미어": "cashmere",
        "cashmere": "cashmere",
        "리오셀": "lyocell",
        "lyocell": "lyocell",
        "큐프로": "cupro",
        "cupro": "cupro",
        "elastane": "spandex",
        "span": "spandex",
    }

    key = value.strip().lower().replace("%", "")
    return aliases.get(key, key)


def parse_materials(materials_text: str, ratios_text: str) -> dict[str, float]:
    materials = [item.strip() for item in materials_text.split(";") if item.strip()]
    ratios = [item.strip() for item in ratios_text.split(";") if item.strip()]

    if not materials:
        return {}

    parsed: dict[str, float] = {}
    for index, material in enumerate(materials):
        ratio = 0.0
        if index < len(ratios):
            try:
                ratio = float(ratios[index].replace("%", "").strip())
            except ValueError:
                ratio = 0.0

        parsed[normalize_material_name(material)] = ratio

    return parsed


def parse_bool(value: str, default: bool = True) -> bool:
    text = value.strip().lower()
    if not text:
        return default
    return text in {"true", "yes", "y", "1", "include", "포함", "예"}


def format_materials(materials: dict[str, float]) -> str:
    if not materials:
        return ""

    return ";".join(
        f"{key}:{value:g}" for key, value in sorted(materials.items())
    )


def read_answer_cases(path: Path) -> list[AnswerCase]:
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

            original_materials = parse_materials(
                row.get("answer_materials", ""),
                row.get("answer_ratios", ""),
            )
            normalized_materials = parse_materials(
                row.get("normalized_materials", ""),
                row.get("normalized_ratios", ""),
            )

            cases.append(
                AnswerCase(
                    row=row,
                    case_id=case_id,
                    file_name=file_name,
                    original_materials=original_materials,
                    normalized_materials=normalized_materials or original_materials,
                    case_type=(row.get("case_type") or "일반 라벨").strip(),
                    include_in_accuracy=parse_bool(
                        row.get("include_in_accuracy", ""),
                        default=True,
                    ),
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

    materials: dict[str, float] = {}
    for key, value in raw.items():
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            ratio = 0.0
        materials[normalize_material_name(str(key))] = ratio

    return materials


def classify_result(
    answer: dict[str, float],
    actual: dict[str, float],
    status_code: int | None,
    error_message: str,
    tolerance: float,
) -> tuple[str, str]:
    if status_code is None:
        return "서버/API 실패", error_message or "request_failed"

    if status_code < 200 or status_code >= 300:
        if status_code == 422:
            return "OCR 실패", "AI 인식 실패 또는 소재/혼용률 추출 실패"
        return "서버/API 실패", f"HTTP {status_code}: {error_message}"

    if not actual:
        return "OCR 실패", "AI 결과 소재 없음"

    answer_keys = set(answer)
    actual_keys = set(actual)
    missing = sorted(answer_keys - actual_keys)
    extra = sorted(actual_keys - answer_keys)

    if missing or extra:
        reasons = []
        if missing:
            reasons.append(f"누락 소재: {';'.join(missing)}")
        if extra:
            reasons.append(f"추가 소재: {';'.join(extra)}")
        return "소재 실패", " / ".join(reasons)

    ratio_errors = {
        key: actual[key] - answer[key]
        for key in sorted(answer_keys)
        if abs(actual[key] - answer[key]) > tolerance
    }

    if not ratio_errors:
        return "완전 성공", "없음"

    if answer_keys == actual_keys:
        detail = "; ".join(
            f"{key} 오차 {error_value:+.1f}%p"
            for key, error_value in ratio_errors.items()
        )
        return "소재 성공/비율 실패", detail

    return "부분 성공", "주요 소재 일부 일치"


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
        judgment, failure_reason = classify_result(
            answer=case.normalized_materials,
            actual=ai_materials,
            status_code=status_code,
            error_message=error_message,
            tolerance=tolerance,
        )
    else:
        judgment = "정확도 제외"
        failure_reason = "복합/부위별 라벨 또는 현재 일반 정확도 계산 대상 제외"

    row = {
        "id": case.case_id,
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
