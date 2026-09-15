"""Regression checks for the backend path that consumes AI OCR parsing."""

from __future__ import annotations

from io import BytesIO
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import UploadFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "BACKEND"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

backend_main = importlib.import_module("main")
ocr_text = importlib.import_module("apps.text.ocr_text")
parse_label = importlib.import_module("apps.text.parse_label").parse_label


class RecordingDb:
    def __init__(self) -> None:
        self.saved = []
        self.committed = False

    def add(self, record) -> None:
        self.saved.append(record)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, record) -> None:
        record.id = 42


def test_backend_imports_the_repository_ai_modules() -> None:
    assert backend_main.AI_MODULE_PATH == REPOSITORY_ROOT / "AI" / "kdpp_ai_ocr_integrated"
    assert backend_main.run_ocr is ocr_text.run_ocr
    assert backend_main.parse_label is parse_label


def test_scan_label_uses_ai_parser_and_returns_analysis_response(monkeypatch) -> None:
    factors = {"cotton": 8.3, "polyester": 9.5}
    monkeypatch.setattr(
        backend_main,
        "find_material",
        lambda _db, name: SimpleNamespace(carbon_factor=factors[name]),
    )
    db = RecordingDb()
    image = UploadFile(filename="label.jpg", file=BytesIO(b"not-read-when-text-is-provided"))

    response = backend_main.scan_label(
        image=image,
        raw_ocr_text="COTTON 80% POLYESTER 20%",
        db=db,
    )

    assert response["materials"] == {"cotton": 80, "polyester": 20}
    assert response["carbon_footprint"] == 8.54
    assert response["saved_result_id"] == 42
    assert response["title"] == "스캔한 의류"
    assert response["category"] == "상의"
    assert db.committed is True
    assert len(db.saved) == 1
