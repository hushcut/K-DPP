"""Failure tracking must retain regressions and reject changes to evaluation scope."""

from copy import deepcopy
import json

import pytest

from apps.service.response_contract import normalize_label_response
from scripts import track_ocr_failures as tracking


def row(image_id, materials=None, *, selected="outer", expected="outer", included=True):
    success = materials is not None
    return {
        "image_id": image_id, "sha256": "a" * 64, "source_group": image_id,
        "included": included, "answer": {"cotton": 100}, "answer_part": expected,
        "result": normalize_label_response({
            "status": "success" if success else "failed",
            "materials": materials or {},
            "selected_part": selected if success else "",
            "parts": {selected: materials} if success else {},
            "raw_ocr_preview": "PRIVATE_OCR_SENTINEL",
            "message": "PRIVATE_MESSAGE_SENTINEL",
            "ocr": {"private": "PRIVATE_OCR_METADATA_SENTINEL"},
        }, api_version="1.0"),
    }


def test_tracks_material_failure_part_mismatch_and_exclusion_without_private_fields():
    rows = [row("QA001", {"cotton": 100}), row("QA002"),
            row("QA003", {"cotton": 100}, selected="generic"),
            row("QA004", included=False)]
    source = deepcopy(rows)
    report = tracking.track_failures(rows)
    summary = report["summary"]
    assert summary["image_count"] == 4 and summary["evaluated"] == 3
    assert summary["material_exact"] == 2 and summary["material_and_part_exact"] == 1
    assert summary["material_unconfirmed"] == summary["part_only_mismatch"] == 1
    assert [(case["image_id"], case["category"]) for case in report["cases"]] == [
        ("QA002", "material_unconfirmed"), ("QA003", "part_mismatch"),
    ]
    serialized = json.dumps(report)
    assert "PRIVATE" not in serialized and "cotton" not in serialized
    assert "raw_ocr_preview" not in serialized and "sha256" not in serialized
    assert rows == source


def test_same_total_score_does_not_hide_regression_and_recovery():
    before = [row("QA001", {"cotton": 100}), row("QA002")]
    after = [row("QA001"), row("QA002", {"cotton": 100})]
    report = tracking.track_failures(after, before)
    assert report["summary"]["material_exact"] == 1
    assert report["comparison"]["material_regressions"] == ["QA001"]
    assert report["comparison"]["material_recoveries"] == ["QA002"]


def test_part_regression_does_not_change_material_score():
    before = [row("QA001", {"cotton": 100})]
    after = [row("QA001", {"cotton": 100}, selected="generic")]
    report = tracking.track_failures(after, before)
    assert report["comparison"]["material_regressions"] == []
    assert report["comparison"]["material_and_part_regressions"] == ["QA001"]


def test_changed_wrong_composition_is_tracked_even_when_category_is_same():
    before = [row("QA001", {"nylon": 100})]
    after = [row("QA001", {"polyester": 100})]
    assert tracking.track_failures(after, before)["comparison"]["changed_case_ids"] == ["QA001"]


def test_exact_and_tolerance_scores_remain_separate():
    item = row("QA001", {"cotton": 78, "polyester": 22})
    item["answer"] = {"cotton": 80, "polyester": 20}
    summary = tracking.track_failures([item])["summary"]
    assert summary["material_exact"] == 0 and summary["material_within_tolerance"] == 1


@pytest.mark.parametrize("field,value", [
    ("answer", {"nylon": 100}), ("answer_part", "generic"),
    ("included", False), ("source_group", "OTHER"), ("sha256", "b" * 64),
    ("image_id", "OTHER"),
])
def test_changed_benchmark_cannot_be_reported_as_improvement(field, value):
    before = [row("QA001", {"cotton": 100}), row("QA002")]
    after = deepcopy(before)
    after[0][field] = value
    with pytest.raises(tracking.FailureSnapshotError):
        tracking.track_failures(after, before)


@pytest.mark.parametrize("marker", ["review", "manual_composition_review_confirmed:first_generic",
                                   "confirmed_representative_selection:first_generic",
                                   "confirmed_material_alias:poly:polyester"])
def test_manual_confirmation_is_rejected_from_automatic_snapshot(marker):
    item = row("QA001", {"cotton": 100})
    if marker == "review":
        item["result"]["parse_evidence"]["review"] = {"confirmed": True}
    else:
        item["result"]["warnings"].append(marker)
    with pytest.raises(tracking.FailureSnapshotError):
        tracking.track_failures([item])


@pytest.mark.parametrize("rows", [[], [row("QA001"), row("QA001")],
                                 [row("QA001", included=False)]])
def test_empty_duplicate_or_all_excluded_snapshots_are_rejected(rows):
    with pytest.raises(tracking.FailureSnapshotError):
        tracking.track_failures(rows)


def test_partial_success_and_nonboolean_inclusion_are_rejected():
    item = row("QA001", {"cotton": 100})
    item["result"]["materials"] = {"cotton": 99}
    with pytest.raises(tracking.FailureSnapshotError):
        tracking.track_failures([item])
    item = row("QA001")
    item["included"] = "false"
    with pytest.raises(tracking.FailureSnapshotError):
        tracking.track_failures([item])


def test_cli_does_not_overwrite_existing_output_or_disclose_source(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text(json.dumps([row("QA001")]), encoding="utf8")
    output = tmp_path / "keep.json"
    output.write_text("keep", encoding="utf8")
    monkeypatch.setattr("sys.argv", ["track_ocr_failures", "--current", str(source),
                                    "--output", str(output)])
    with pytest.raises(SystemExit):
        tracking.main()
    assert output.read_text(encoding="utf8") == "keep"
    assert "PRIVATE" not in capsys.readouterr().out


def test_cli_writes_only_management_report(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.json"
    text = json.dumps([row("QA001")])
    source.write_text(text, encoding="utf8")
    output = tmp_path / "new.json"
    monkeypatch.setattr("sys.argv", ["track_ocr_failures", "--current", str(source),
                                    "--baseline", str(source), "--output", str(output)])
    tracking.main()
    assert json.loads(output.read_text(encoding="utf8"))["comparison"]["material_regressions"] == []
    assert "PRIVATE" not in output.read_text(encoding="utf8")
    assert source.read_text(encoding="utf8") == text
    assert "material_exact" in capsys.readouterr().out


def test_service_failure_history_is_visible_without_hiding_composition_failure_or_recovery():
    failed = row("QA001")
    failed["result"]["error_code"] = "composition_not_found"
    recovered = row("QA002", {"cotton": 100})
    for item in (failed, recovered):
        item["result"]["ocr"] = {"attempts": [{"outcome": "failed", "failure_code": "service_unavailable"}]}
    report = tracking.track_failures([failed, recovered])
    assert report["summary"]["evaluated"] == 2 and report["summary"]["material_exact"] == 1
    assert report["summary"]["service_error_case_count"] == 2
    assert report["summary"]["failure_stage_counts"] == {"composition": 1}
    assert report["cases"][0]["failure_stage"] == "composition"
    assert [event["failure_stage"] for event in report["ocr_events"]] == ["composition", "success"]


def test_fatal_service_error_and_missing_cache_are_distinct_from_unread_text():
    items = [row("QA001"), row("QA002"), row("QA003")]
    for item, code in zip(items, ("OcrUnavailableError", "ocr_text_empty", "OcrCacheMissError")):
        item["result"]["error_code"] = code
    report = tracking.track_failures(items)
    assert report["summary"]["failure_stage_counts"] == {"cache_incomplete": 1, "ocr_service": 1, "text_recognition": 1}
    assert report["summary"]["evaluated"] == report["summary"]["material_unconfirmed"] == 3
    assert report["summary"]["service_error_case_count"] == report["summary"]["cache_incomplete_case_count"] == 1
