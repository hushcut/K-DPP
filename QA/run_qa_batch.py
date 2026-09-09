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
from dataclasses import dataclass, field
from enum import StrEnum
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
DEFAULT_UPLOAD_FIELD = "image"
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 1 * 1024 * 1024
DEFAULT_MAX_RAW_RESPONSE_CHARS = 4_000
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


class QaJudgment(StrEnum):
    """User-facing QA judgments written to the result CSV."""

    COMPLETE_SUCCESS = "완전 성공"
    MATERIAL_FAILURE = "소재 실패"
    RATIO_FAILURE = "소재 성공/비율 실패"
    OCR_FAILURE = "OCR 실패"
    API_FAILURE = "서버/API 실패"
    EXCLUDED = "정확도 제외"


class FailureCategory(StrEnum):
    """QA-owned machine-readable failure categories."""

    SERVER_OR_API_FAILURE = "server_or_api_failure"
    OCR_OR_PARSER_FAILURE = "ocr_or_parser_failure"
    API_CONTRACT_INVALID = "api_contract_invalid"
    PARSER_RETURNED_NO_MATERIALS = "parser_returned_no_materials"
    QA_INPUT_TOO_LARGE = "qa_input_too_large"
    API_RESPONSE_TOO_LARGE = "api_response_too_large"
    NOT_COMPARED = "not_compared"


class ApiErrorCode(StrEnum):
    """Service error codes whose QA meaning is defined by this runner."""

    OCR_TEXT_EMPTY = "ocr_text_empty"
    COMPOSITION_NOT_FOUND = "composition_not_found"
    AMBIGUOUS_COMPOSITION = "ambiguous_composition"
    INVALID_REQUEST = "invalid_request"


OCR_OR_PARSER_422_CODES = frozenset(
    {
        ApiErrorCode.OCR_TEXT_EMPTY,
        ApiErrorCode.COMPOSITION_NOT_FOUND,
        ApiErrorCode.AMBIGUOUS_COMPOSITION,
    }
)


def csv_safe(value: Any) -> Any:
    """Prevent spreadsheet programs from interpreting untrusted text as a formula."""

    if isinstance(value, str) and value.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def validate_upload_field(upload_field: str) -> str:
    """Keep a CLI-supplied field name inside one multipart header value."""

    field_name = upload_field.strip()
    if not field_name or any(character in field_name for character in ('"', "\r", "\n")):
        raise ValueError("업로드 필드명은 비어 있거나 줄바꿈/따옴표를 포함할 수 없습니다.")
    return field_name


@dataclass(frozen=True)
class QaRunConfig:
    """All settings that affect one integration QA run."""

    api_url: str = DEFAULT_API_URL
    upload_field: str = DEFAULT_UPLOAD_FIELD
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    tolerance: float = DEFAULT_TOLERANCE
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_raw_response_chars: int = DEFAULT_MAX_RAW_RESPONSE_CHARS

    def __post_init__(self) -> None:
        normalized_api_url = self.api_url.strip()
        if not normalized_api_url:
            raise ValueError("API URL은 비어 있을 수 없습니다.")
        if self.timeout_seconds <= 0:
            raise ValueError("시간 제한은 0보다 커야 합니다.")
        if self.tolerance < 0:
            raise ValueError("허용 오차는 음수일 수 없습니다.")
        if (
            self.max_image_bytes <= 0
            or self.max_response_bytes <= 0
            or self.max_raw_response_chars <= 0
        ):
            raise ValueError("이미지와 응답 크기 제한은 0보다 커야 합니다.")
        object.__setattr__(self, "api_url", normalized_api_url)
        object.__setattr__(self, "upload_field", validate_upload_field(self.upload_field))


@dataclass
class AnswerCase:
    row: dict[str, str]
    case_id: str
    file_name: str
    original_materials: dict[str, float]
    normalized_materials: dict[str, float]
    case_type: str
    include_in_accuracy: bool


@dataclass(frozen=True)
class ApiMaterialsResult:
    """Normalized API materials or a contract error that QA must preserve."""

    materials: dict[str, float]
    contract_error: str = ""


@dataclass(frozen=True)
class ApiCallResult:
    """One completed API call, including recoverable QA execution failures."""

    status_code: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    raw_response_truncated: bool = False
    response_contract_error: str = ""
    exception_text: str = ""
    execution_failure_category: str = ""


class QaInputTooLargeError(ValueError):
    """Raised before an oversized local QA image is loaded into memory."""


class ApiResponseTooLargeError(RuntimeError):
    """Raised when an API response exceeds the QA result retention limit."""


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
        "--upload-field",
        default=DEFAULT_UPLOAD_FIELD,
        help=f"Multipart upload field name. Default: {DEFAULT_UPLOAD_FIELD}",
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
        "--max-image-bytes",
        type=int,
        default=DEFAULT_MAX_IMAGE_BYTES,
        help=f"Maximum input image bytes. Default: {DEFAULT_MAX_IMAGE_BYTES}",
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help=f"Maximum API response bytes. Default: {DEFAULT_MAX_RESPONSE_BYTES}",
    )
    parser.add_argument(
        "--max-raw-response-chars",
        type=int,
        default=DEFAULT_MAX_RAW_RESPONSE_CHARS,
        help=(
            "Maximum response characters retained in the QA CSV. "
            f"Default: {DEFAULT_MAX_RAW_RESPONSE_CHARS}"
        ),
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


def build_multipart_body(
    image_path: Path,
    config: QaRunConfig,
) -> tuple[bytes, str]:
    image_size = image_path.stat().st_size
    if image_size > config.max_image_bytes:
        raise QaInputTooLargeError(
            "이미지 크기가 제한을 초과했습니다: "
            f"{image_size} bytes (최대 {config.max_image_bytes} bytes)"
        )

    boundary = f"----KDPPOCRQA{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    image_bytes = image_path.read_bytes()

    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{config.upload_field}"; '
            f'filename="{image_path.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        image_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]

    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def read_limited_response(stream: Any, max_response_bytes: int) -> str:
    """Read at most the configured response limit plus one sentinel byte."""

    raw_bytes = stream.read(max_response_bytes + 1)
    if len(raw_bytes) > max_response_bytes:
        raise ApiResponseTooLargeError(
            f"API 응답 크기가 제한을 초과했습니다: 최대 {max_response_bytes} bytes"
        )
    return raw_bytes.decode("utf-8", errors="replace")


def truncate_raw_response(raw_response: str, max_chars: int) -> tuple[str, bool]:
    """Keep QA CSVs readable without changing the bounded API response limit."""

    if len(raw_response) <= max_chars:
        return raw_response, False

    preview = raw_response[:max_chars]
    return (
        f"{preview}\n... [truncated; original length: {len(raw_response)} chars]",
        True,
    )


def parse_api_response_body(raw: str) -> tuple[dict[str, Any], str]:
    """Accept only JSON objects so one malformed response cannot stop a batch."""

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "API 응답 본문이 JSON 객체가 아닙니다."
    if not isinstance(decoded, dict):
        return {}, "API 응답 본문은 JSON 객체여야 합니다."
    return decoded, ""


def call_scan_api(
    config: QaRunConfig,
    image_path: Path,
) -> tuple[int, dict[str, Any], str, str]:
    body, content_type = build_multipart_body(image_path, config)
    req = request.Request(
        config.api_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "ngrok-skip-browser-warning": "true",
        },
    )

    try:
        with request.urlopen(req, timeout=config.timeout_seconds) as response:
            raw = read_limited_response(response, config.max_response_bytes)
            payload, contract_error = parse_api_response_body(raw)
            return response.status, payload, raw, contract_error
    except error.HTTPError as exc:
        raw = read_limited_response(exc, config.max_response_bytes)
        payload, _ = parse_api_response_body(raw)
        if not payload:
            payload = {"status": "error", "message": raw}
        return exc.code, payload, raw, ""


def execute_scan_api(
    config: QaRunConfig,
    image_path: Path,
) -> ApiCallResult:
    """Execute one scan request without letting one case stop the QA batch."""

    try:
        status_code, payload, raw_response, response_contract_error = call_scan_api(
            config,
            image_path,
        )
        raw_response, raw_response_truncated = truncate_raw_response(
            raw_response,
            config.max_raw_response_chars,
        )
        return ApiCallResult(
            status_code=status_code,
            payload=payload,
            raw_response=raw_response,
            raw_response_truncated=raw_response_truncated,
            response_contract_error=response_contract_error,
        )
    except QaInputTooLargeError as exc:
        return ApiCallResult(
            exception_text=str(exc),
            execution_failure_category=FailureCategory.QA_INPUT_TOO_LARGE,
        )
    except ApiResponseTooLargeError as exc:
        return ApiCallResult(
            exception_text=str(exc),
            execution_failure_category=FailureCategory.API_RESPONSE_TOO_LARGE,
        )
    except Exception as exc:  # noqa: BLE001 - QA output should record all failures.
        raw_response, raw_response_truncated = truncate_raw_response(
            traceback.format_exc(limit=2),
            config.max_raw_response_chars,
        )
        return ApiCallResult(
            raw_response=raw_response,
            raw_response_truncated=raw_response_truncated,
            exception_text=f"{type(exc).__name__}: {exc}",
        )


def parse_api_materials(payload: dict[str, Any]) -> ApiMaterialsResult:
    raw = payload.get("materials")
    if not isinstance(raw, dict):
        return ApiMaterialsResult(
            materials={},
            contract_error="API 응답 materials는 객체여야 합니다.",
        )

    try:
        return ApiMaterialsResult(
            materials=normalize_material_mapping(raw, allow_unknown=True),
        )
    except QaComparisonError as exc:
        # API 응답이 계약을 위반해도 전체 QA를 중단하지 않고 실패 행으로 남긴다.
        return ApiMaterialsResult(materials={}, contract_error=str(exc))


def classify_result(
    answer: dict[str, float],
    actual: dict[str, float],
    status_code: int | None,
    error_message: str,
    tolerance: float,
    api_contract_error: str = "",
    api_error_code: str = "",
) -> tuple[QaJudgment, str, str]:
    if status_code is None:
        return (
            QaJudgment.API_FAILURE,
            error_message or "request_failed",
            FailureCategory.SERVER_OR_API_FAILURE,
        )

    if status_code < 200 or status_code >= 300:
        if status_code == 422:
            if api_error_code in OCR_OR_PARSER_422_CODES:
                return (
                    QaJudgment.OCR_FAILURE,
                    "AI 인식 실패 또는 소재/혼용률 추출 실패",
                    FailureCategory.OCR_OR_PARSER_FAILURE,
                )
            if api_error_code == ApiErrorCode.INVALID_REQUEST:
                return (
                    QaJudgment.API_FAILURE,
                    "HTTP 422: invalid_request",
                    FailureCategory.API_CONTRACT_INVALID,
                )
        return (
            QaJudgment.API_FAILURE,
            f"HTTP {status_code}: {error_message}",
            FailureCategory.SERVER_OR_API_FAILURE,
        )

    if api_contract_error:
        return (
            QaJudgment.API_FAILURE,
            api_contract_error,
            FailureCategory.API_CONTRACT_INVALID,
        )

    if not actual:
        return (
            QaJudgment.OCR_FAILURE,
            "AI 결과 소재 없음",
            FailureCategory.PARSER_RETURNED_NO_MATERIALS,
        )

    comparison = compare_material_compositions(answer, actual, tolerance=tolerance)
    if comparison.judgment == "success":
        return QaJudgment.COMPLETE_SUCCESS, "없음", comparison.failure_category
    if comparison.missing or comparison.extra:
        return QaJudgment.MATERIAL_FAILURE, comparison.failure_reason, comparison.failure_category
    return QaJudgment.RATIO_FAILURE, comparison.failure_reason, comparison.failure_category


def extract_error_message(payload: dict[str, Any], raw: str) -> str:
    message = payload.get("message") or payload.get("detail") or payload.get("error")
    if isinstance(message, dict):
        return json.dumps(message, ensure_ascii=False)
    if message:
        return str(message)
    return raw[:300]


def extract_api_error_code(payload: dict[str, Any]) -> str:
    error_code = payload.get("error_code")
    return error_code.strip() if isinstance(error_code, str) else ""


def build_result_row(
    case: AnswerCase,
    image_path: Path,
    config: QaRunConfig,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    api_call = execute_scan_api(config, image_path)
    elapsed = time.perf_counter() - started_at
    api_materials = parse_api_materials(api_call.payload)
    ai_materials = api_materials.materials
    api_contract_error = api_call.response_contract_error or api_materials.contract_error
    api_error_code = extract_api_error_code(api_call.payload)
    error_message = api_call.exception_text or extract_error_message(
        api_call.payload,
        api_call.raw_response,
    )
    if api_call.execution_failure_category:
        judgment = QaJudgment.API_FAILURE
        failure_reason = api_call.exception_text
        failure_category = api_call.execution_failure_category
    elif case.include_in_accuracy:
        judgment, failure_reason, failure_category = classify_result(
            answer=case.normalized_materials,
            actual=ai_materials,
            status_code=api_call.status_code,
            error_message=error_message,
            tolerance=config.tolerance,
            api_contract_error=api_contract_error,
            api_error_code=api_error_code,
        )
    elif (
        api_call.status_code is None
        or api_call.status_code < 200
        or api_call.status_code >= 300
        or api_contract_error
    ):
        # 정확도 산정 대상이 아닌 라벨도 실행 실패는 숨기지 않는다.
        # 다만 print_summary는 include_in_accuracy만 집계하므로 정확도에는 반영되지 않는다.
        judgment, failure_reason, failure_category = classify_result(
            answer=case.normalized_materials,
            actual=ai_materials,
            status_code=api_call.status_code,
            error_message=error_message,
            tolerance=config.tolerance,
            api_contract_error=api_contract_error,
            api_error_code=api_error_code,
        )
    else:
        judgment = QaJudgment.EXCLUDED
        failure_reason = "복합/부위별 라벨 또는 현재 일반 정확도 계산 대상 제외"
        failure_category = FailureCategory.NOT_COMPARED

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
        "api_contract_error": api_contract_error,
        "api_error_code": api_error_code,
        "http_status": api_call.status_code if api_call.status_code is not None else "",
        "failure_reason": failure_reason,
        "error_message": error_message,
        "carbon_footprint": api_call.payload.get("carbon_footprint", ""),
        "care_instruction": api_call.payload.get("care_instruction", ""),
        "raw_response": api_call.raw_response,
        "raw_response_truncated": "TRUE" if api_call.raw_response_truncated else "FALSE",
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
        "api_contract_error",
        "api_error_code",
        "http_status",
        "failure_reason",
        "error_message",
        "carbon_footprint",
        "care_instruction",
        "raw_response",
        "raw_response_truncated",
        "elapsed_seconds",
        "memo",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {
                fieldname: csv_safe(row.get(fieldname, ""))
                for fieldname in fieldnames
            }
            for row in rows
        )


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    included_rows = [
        row for row in rows if str(row.get("include_in_accuracy", "")).upper() == "TRUE"
    ]
    operational_failures = [
        row for row in rows if row.get("judgment") == QaJudgment.API_FAILURE
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

    if operational_failures:
        failure_counts: dict[str, int] = {}
        for row in operational_failures:
            category = str(
                row.get("failure_category") or FailureCategory.SERVER_OR_API_FAILURE
            )
            failure_counts[category] = failure_counts.get(category, 0) + 1
        print(f"Operational failures (all cases): {len(operational_failures)}")
        for category, count in sorted(failure_counts.items()):
            print(f"- {category}: {count}")


def main() -> int:
    args = parse_args()
    answers_path = Path(args.answers)
    images_dir = Path(args.images)
    output_path = Path(args.output)
    config = QaRunConfig(
        api_url=args.api_url,
        upload_field=args.upload_field,
        timeout_seconds=args.timeout,
        tolerance=args.tolerance,
        max_image_bytes=args.max_image_bytes,
        max_response_bytes=args.max_response_bytes,
        max_raw_response_chars=args.max_raw_response_chars,
    )

    cases = read_answer_cases(answers_path)
    if not cases:
        print("No answer cases found.", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    print(f"API URL: {config.api_url}")
    print(f"Upload field: {config.upload_field}")
    print(f"Timeout: {config.timeout_seconds}s")
    print(f"Image/response limit: {config.max_image_bytes}/{config.max_response_bytes} bytes")
    print(f"Raw response CSV preview: {config.max_raw_response_chars} chars")
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
                    "judgment": QaJudgment.API_FAILURE,
                    "failure_category": FailureCategory.SERVER_OR_API_FAILURE,
                    "api_contract_error": "",
                    "api_error_code": "",
                    "http_status": "",
                    "failure_reason": "이미지 파일 없음",
                    "error_message": str(image_path),
                    "carbon_footprint": "",
                    "care_instruction": "",
                    "raw_response": "",
                    "raw_response_truncated": "FALSE",
                    "elapsed_seconds": "",
                    "memo": case.row.get("memo", ""),
                }
            )
            continue

        rows.append(
            build_result_row(
                case=case,
                image_path=image_path,
                config=config,
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
