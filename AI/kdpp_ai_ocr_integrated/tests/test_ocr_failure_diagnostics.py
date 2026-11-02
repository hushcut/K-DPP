"""Service outages, unread text and incomplete composition need different records."""

from copy import deepcopy
import csv
import json

import pytest

from apps.text.ocr_errors import OcrTotalTimeoutError, OcrUnavailableError
from scripts.ocr_failure_diagnostics import failure_diagnostics
from scripts import run_qa_batch as qa


@pytest.mark.parametrize("code,stage", [
    ("OcrUnavailableError", "ocr_service"), ("ocr_service_failed", "ocr_service"),
    ("ocr_timeout", "ocr_service"), ("ocr_quota_exceeded", "ocr_service"),
    ("ocr_not_configured", "ocr_configuration"), ("ocr_text_empty", "text_recognition"),
    ("composition_not_found", "composition"), ("ambiguous_composition", "composition"),
    ("OcrTotalTimeoutError", "ocr_budget"), ("OcrCacheMissError", "cache_incomplete"),
    ("invalid_image", "input"), ("pipeline_exception", "pipeline"),
])
def test_final_error_is_classified_from_known_evidence(code, stage):
    result = {"status": "failed", "error_code": code}
    assert failure_diagnostics(result)["failure_stage"] == stage


@pytest.mark.parametrize("success", [False, True])
def test_failed_candidate_is_an_event_not_proof_of_the_final_failure_cause(success):
    result = {"status": "success" if success else "failed", "error_code": "" if success else "composition_not_found",
              "ocr": {"attempts": [{"outcome": "failed", "failure_code": "service_unavailable"}],
                      "attempt_failures": ["material_crop:OcrUnavailableError"]}}
    before = deepcopy(result)
    diagnostic = failure_diagnostics(result)
    assert diagnostic["failure_stage"] == ("success" if success else "composition")
    assert diagnostic["service_error_codes"] == ["ocr_service_unavailable"]
    assert result == before


@pytest.mark.parametrize("code,field", [("cache_miss", "cache_incomplete"), ("total_timeout", "budget_exhausted")])
def test_cache_and_local_budget_events_do_not_manufacture_a_vision_outage(code, field):
    result = {"status": "failed", "error_code": "composition_not_found", "ocr": {
        "attempts": [{"outcome": "skipped" if code == "total_timeout" else "failed", "failure_code": code}]}}
    diagnostic = failure_diagnostics(result)
    assert diagnostic[field] is True
    assert diagnostic["service_error_codes"] == []
    assert diagnostic["failure_stage"] == "composition"


@pytest.mark.parametrize("ocr", [None, {"attempts": None}, {"attempts": [None, "PRIVATE"], "attempt_failures": [None]}])
def test_incomplete_old_metadata_does_not_invent_an_error(ocr):
    diagnostic = failure_diagnostics({"status": "failed", "error_code": "composition_not_found", "ocr": ocr})
    assert diagnostic["failure_stage"] == "composition"
    assert not diagnostic["service_error_codes"]


def test_nonempty_ocr_cannot_prove_that_characters_were_read_correctly():
    diagnostic = failure_diagnostics({"status": "failed", "raw_ocr_preview": "UNKNOWN 100%",
                                      "error_code": "composition_not_found"})
    assert diagnostic["failure_stage"] == "composition"


def test_a_skipped_candidate_cannot_claim_a_remote_service_error():
    diagnostic = failure_diagnostics({"status": "failed", "error_code": "composition_not_found", "ocr": {
        "attempts": [{"outcome": "skipped", "failure_code": "service_unavailable"}]}})
    assert diagnostic["service_error_codes"] == []


def test_unknown_provider_text_is_never_copied_into_management_fields():
    result = {"status": "failed", "error_code": "PRIVATE_PATH", "ocr": {
        "attempt_failures": ["PRIVATE_PROVIDER_MESSAGE"],
        "attempts": [{"outcome": "failed", "failure_code": "PRIVATE_CREDENTIAL"}]}}
    diagnostic = failure_diagnostics(result, exception_code="RuntimeError: PRIVATE_EXCEPTION")
    assert diagnostic["failure_stage"] == "pipeline"
    assert "PRIVATE" not in json.dumps(diagnostic)
    assert qa.classify_failure(result=result, exception="RuntimeError: PRIVATE_EXCEPTION",
                              judgment="failed", failure_reason="no_predicted_materials") == "pipeline_exception"


def test_qa_exception_category_retains_a_known_service_code():
    assert qa.classify_failure(result={"status": "failed", "error_code": "pipeline_exception"},
                              exception="OcrUnavailableError: PRIVATE", judgment="failed",
                              failure_reason="no_predicted_materials") == "ocr_service_unavailable"


@pytest.mark.parametrize("error,stage,code,rpc,retries", [
    (OcrUnavailableError("PRIVATE_PROVIDER_MESSAGE", rpc_attempt_count=3, retry_count=2),
     "ocr_service", "ocr_service_unavailable", "3", "2"),
    (OcrTotalTimeoutError("PRIVATE_BUDGET_MESSAGE", rpc_attempt_count=0, retry_count=0),
     "ocr_budget", "ocr_total_timeout", "0", "0"),
    (RuntimeError("PRIVATE_PATH"), "pipeline", "pipeline_exception", "", ""),
])
def test_batch_records_safe_errors_and_keeps_failed_images_in_the_denominator(
    monkeypatch, tmp_path, capsys, error, stage, code, rpc, retries,
):
    image = tmp_path / "QA001.jpg"
    image.write_bytes(b"not used by the mocked OCR")
    answer = tmp_path / "answers.csv"
    answer.write_text("file_name,answer_materials,answer_ratios\nQA001.jpg,cotton,100\n", encoding="utf8")
    output = tmp_path / "new.csv"

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(qa, "analyze_label_image_cached", fail)
    monkeypatch.setattr("sys.argv", ["run_qa_batch", "--image-dir", str(tmp_path), "--answer-key", str(answer),
                                    "--output", str(output), "--ocr-cache", str(tmp_path / "unused.json"), "--offline"])
    with pytest.raises(SystemExit):
        qa.main()
    with output.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["judgment"] == "failed" and row["failure_stage"] == stage
    assert row["failure_category"] == code
    assert row["ocr_rpc_attempt_count"] == rpc and row["ocr_retry_count"] == retries
    summary = json.loads(output.with_suffix(".summary.json").read_text(encoding="utf8"))
    assert summary["compared_count"] == 1 and summary["exact_composition_accuracy"] == 0
    assert summary["failure_stage_counts"] == {stage: 1}
    assert "PRIVATE" not in output.read_text(encoding="utf-8-sig") + capsys.readouterr().out
