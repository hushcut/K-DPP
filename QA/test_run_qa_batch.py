"""Integration QA runner tests that do not send images or call the API."""

from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from QA.run_qa_batch import (
    AnswerCase,
    ApiErrorCode,
    ApiResponseTooLargeError,
    FailureCategory,
    QaInputTooLargeError,
    QaJudgment,
    QaRunConfig,
    build_multipart_body,
    build_result_row,
    classify_result,
    csv_safe,
    execute_scan_api,
    parse_api_materials,
    parse_api_response_body,
    print_summary,
    read_limited_response,
    truncate_raw_response,
    validate_upload_field,
)


TEST_CONFIG = QaRunConfig(
    api_url="http://example.invalid/api/scan",
    timeout_seconds=1,
    tolerance=3.0,
)


def test_api_materials_use_the_same_parser_aliases() -> None:
    parsed = parse_api_materials({"materials": {"면": 95, "elastane": 5}})

    assert parsed.materials == {
        "cotton": 95.0,
        "spandex": 5.0,
    }
    assert parsed.contract_error == ""


def test_api_result_emits_the_shared_failure_category() -> None:
    judgment, reason, category = classify_result(
        answer={"cotton": 80, "polyester": 20},
        actual={"cotton": 70, "acrylic": 30},
        status_code=200,
        error_message="",
        tolerance=3.0,
    )

    assert judgment == QaJudgment.MATERIAL_FAILURE
    assert "missing=polyester" in reason
    assert category == "material_missing_and_extra"


def test_invalid_api_materials_are_not_recorded_as_ocr_failure() -> None:
    parsed = parse_api_materials({"materials": {"cotton": "not-a-number"}})
    judgment, reason, category = classify_result(
        answer={"cotton": 100},
        actual=parsed.materials,
        status_code=200,
        error_message="",
        tolerance=3.0,
        api_contract_error=parsed.contract_error,
    )

    assert judgment == QaJudgment.API_FAILURE
    assert category == FailureCategory.API_CONTRACT_INVALID
    assert "숫자가 아닙니다" in reason


def test_non_object_api_response_is_a_contract_error() -> None:
    payload, contract_error = parse_api_response_body("[]")
    judgment, reason, category = classify_result(
        answer={"cotton": 100},
        actual={},
        status_code=200,
        error_message="",
        tolerance=3.0,
        api_contract_error=contract_error,
    )

    assert payload == {}
    assert judgment == QaJudgment.API_FAILURE
    assert category == FailureCategory.API_CONTRACT_INVALID
    assert "JSON 객체" in reason


def test_invalid_request_422_is_not_recorded_as_ocr_failure() -> None:
    judgment, reason, category = classify_result(
        answer={"cotton": 100},
        actual={},
        status_code=422,
        error_message="요청 형식이 올바르지 않습니다.",
        tolerance=3.0,
        api_error_code=ApiErrorCode.INVALID_REQUEST,
    )

    assert judgment == QaJudgment.API_FAILURE
    assert category == FailureCategory.API_CONTRACT_INVALID
    assert reason == "HTTP 422: invalid_request"


def test_known_parser_422_remains_an_ocr_failure() -> None:
    judgment, _reason, category = classify_result(
        answer={"cotton": 100},
        actual={},
        status_code=422,
        error_message="소재 혼용률을 찾지 못했습니다.",
        tolerance=3.0,
        api_error_code=ApiErrorCode.COMPOSITION_NOT_FOUND,
    )

    assert judgment == QaJudgment.OCR_FAILURE
    assert category == FailureCategory.OCR_OR_PARSER_FAILURE


def test_csv_safe_escapes_formula_prefixes_without_changing_numbers() -> None:
    for value in ("=SUM(A1:A2)", "+1+1", "-1+1", "@command", "  =SUM(A1:A2)"):
        assert csv_safe(value) == "'" + value

    assert csv_safe("ordinary text") == "ordinary text"
    assert csv_safe(42) == 42


def test_excluded_case_still_records_api_failure(monkeypatch) -> None:
    """Accuracy exclusions must not hide an unavailable integration API."""

    case = AnswerCase(
        row={},
        case_id="excluded-api-error",
        file_name="unused.png",
        original_materials={"cotton": 100.0},
        normalized_materials={"cotton": 100.0},
        case_type="복합 라벨",
        include_in_accuracy=False,
    )

    monkeypatch.setattr(
        "QA.run_qa_batch.call_scan_api",
        lambda *_args, **_kwargs: (500, {"message": "temporary failure"}, "", ""),
    )

    row = build_result_row(
        case=case,
        image_path=Path("unused.png"),
        config=TEST_CONFIG,
    )

    assert row["include_in_accuracy"] == "FALSE"
    assert row["judgment"] == QaJudgment.API_FAILURE
    assert row["failure_category"] == FailureCategory.SERVER_OR_API_FAILURE


def test_oversized_image_is_rejected_before_reading(tmp_path) -> None:
    image_path = tmp_path / "too-large.png"
    image_path.write_bytes(b"1234")

    with pytest.raises(QaInputTooLargeError, match="크기가 제한을 초과"):
        build_multipart_body(image_path, QaRunConfig(max_image_bytes=3))


def test_oversized_api_response_is_rejected_after_limit() -> None:
    with pytest.raises(ApiResponseTooLargeError, match="응답 크기가 제한을 초과"):
        read_limited_response(BytesIO(b"1234"), max_response_bytes=3)


def test_oversized_api_response_is_recorded_as_a_distinct_failure(monkeypatch) -> None:
    case = AnswerCase(
        row={},
        case_id="large-response",
        file_name="unused.png",
        original_materials={"cotton": 100.0},
        normalized_materials={"cotton": 100.0},
        case_type="일반 라벨",
        include_in_accuracy=True,
    )

    def raise_response_too_large(*_args, **_kwargs):
        raise ApiResponseTooLargeError("API 응답 크기가 제한을 초과했습니다.")

    monkeypatch.setattr("QA.run_qa_batch.call_scan_api", raise_response_too_large)

    row = build_result_row(
        case=case,
        image_path=Path("unused.png"),
        config=TEST_CONFIG,
    )

    assert row["judgment"] == QaJudgment.API_FAILURE
    assert row["failure_category"] == FailureCategory.API_RESPONSE_TOO_LARGE


def test_execute_scan_api_records_known_qa_input_failure(monkeypatch) -> None:
    def raise_input_too_large(*_args, **_kwargs):
        raise QaInputTooLargeError("이미지 크기가 제한을 초과했습니다.")

    monkeypatch.setattr("QA.run_qa_batch.call_scan_api", raise_input_too_large)

    result = execute_scan_api(
        TEST_CONFIG,
        Path("unused.png"),
    )

    assert result.status_code is None
    assert result.execution_failure_category == FailureCategory.QA_INPUT_TOO_LARGE
    assert "제한을 초과" in result.exception_text


def test_execute_scan_api_marks_a_truncated_raw_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "QA.run_qa_batch.call_scan_api",
        lambda *_args, **_kwargs: (200, {"materials": {"cotton": 100}}, "abcdefgh", ""),
    )

    result = execute_scan_api(
        QaRunConfig(
            api_url="http://example.invalid/api/scan",
            max_raw_response_chars=4,
        ),
        Path("unused.png"),
    )

    assert result.raw_response.startswith("abcd")
    assert result.raw_response_truncated is True
    assert "original length: 8 chars" in result.raw_response


def test_truncate_raw_response_preserves_short_values() -> None:
    raw_response, truncated = truncate_raw_response("short", max_chars=5)

    assert raw_response == "short"
    assert truncated is False


def test_multipart_upload_field_can_follow_backend_contract(tmp_path) -> None:
    image_path = tmp_path / "label.png"
    image_path.write_bytes(b"image")

    body, _content_type = build_multipart_body(
        image_path,
        QaRunConfig(upload_field="label_image"),
    )

    assert b'name="label_image"' in body
    assert b'name="image"' not in body


def test_upload_field_rejects_header_breaking_characters() -> None:
    with pytest.raises(ValueError, match="줄바꿈/따옴표"):
        validate_upload_field('image"\r\nInjected: value')


def test_result_row_passes_configured_upload_field_to_api(monkeypatch) -> None:
    case = AnswerCase(
        row={},
        case_id="configured-upload-field",
        file_name="unused.png",
        original_materials={"cotton": 100.0},
        normalized_materials={"cotton": 100.0},
        case_type="일반 라벨",
        include_in_accuracy=True,
    )
    received_fields: list[str] = []

    def fake_call(config, _image_path):
        received_fields.append(config.upload_field)
        return 200, {"materials": {"cotton": 100}}, "{}", ""

    monkeypatch.setattr("QA.run_qa_batch.call_scan_api", fake_call)

    build_result_row(
        case=case,
        image_path=Path("unused.png"),
        config=QaRunConfig(
            api_url="http://example.invalid/api/scan",
            timeout_seconds=1,
            tolerance=3.0,
            upload_field="label_image",
        ),
    )

    assert received_fields == ["label_image"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"api_url": " "}, "API URL"),
        ({"timeout_seconds": 0}, "시간 제한"),
        ({"tolerance": -0.1}, "허용 오차"),
        ({"max_image_bytes": 0}, "크기 제한"),
        ({"max_raw_response_chars": 0}, "크기 제한"),
    ],
)
def test_run_config_rejects_invalid_values(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        QaRunConfig(**kwargs)


def test_run_config_normalizes_url_whitespace() -> None:
    config = QaRunConfig(api_url="  http://example.invalid/api/scan  ")

    assert config.api_url == "http://example.invalid/api/scan"


def test_summary_reports_excluded_case_api_failures(capsys) -> None:
    rows = [
        {
            "include_in_accuracy": "FALSE",
            "judgment": QaJudgment.API_FAILURE,
            "failure_category": FailureCategory.API_CONTRACT_INVALID,
        },
        {
            "include_in_accuracy": "FALSE",
            "judgment": QaJudgment.EXCLUDED,
            "failure_category": FailureCategory.NOT_COMPARED,
        },
    ]

    print_summary(rows)

    output = capsys.readouterr().out
    assert "Included in accuracy: 0" in output
    assert "Operational failures (all cases): 1" in output
    assert "api_contract_invalid: 1" in output
