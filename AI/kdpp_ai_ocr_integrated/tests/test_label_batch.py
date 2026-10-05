import csv
import json
import sys

from scripts import run_combined_batch


def test_label_batch_writes_ocr_results_without_classifier_columns(tmp_path, monkeypatch):
    image_dir = tmp_path / "labels"
    image_dir.mkdir()
    image_path = image_dir / "label.png"
    image_path.write_bytes(b"mock-image")
    output = tmp_path / "results.csv"
    calls = []

    def analyze(path, credential_path=None):
        calls.append(path)
        assert credential_path is None
        return {
            "status": "success",
            "materials": {"cotton": 100},
            "parts": {"generic": {"cotton": 100}},
            "care_instruction": "물세탁 금지",
        }

    monkeypatch.setattr(run_combined_batch, "analyze_label_image", analyze)
    monkeypatch.setattr(
        sys, "argv",
        ["run_combined_batch", "--image-dir", str(image_dir), "--output", str(output)],
    )
    run_combined_batch.main()

    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert calls == [image_path]
    assert len(rows) == 1
    assert rows[0]["label_status"] == "success"
    assert json.loads(rows[0]["materials"]) == {"cotton": 100}
    assert rows[0]["care_instruction"] == "물세탁 금지"
    assert not {"symbol_status", "symbols", "symbol_exception"}.intersection(rows[0])
