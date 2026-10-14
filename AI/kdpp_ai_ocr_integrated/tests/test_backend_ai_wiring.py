"""Regression checks for the backend path that consumes AI OCR parsing."""

from __future__ import annotations

from io import BytesIO
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, UploadFile
from PIL import Image
import pytest
from starlette.datastructures import Headers

from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "BACKEND"
# The scan API exposes only `warnings` from the AI metadata (DECISIONS 210): confidence and
# parse_evidence wait for an agreed scope, and ocr diagnostics stay in server logs.
INTERNAL_KEYS = {"ocr", "confidence", "parse_evidence"}


@pytest.fixture(scope="module")
def backend_main(tmp_path_factory):
    # Keep backend import out of collection: database runs ensure_schema().
    # Set a disposable DB before import and restore modules after these tests.
    db_path = tmp_path_factory.mktemp("backend-ai-wiring") / "test.db"
    module_names = ("main", "database", "init_data")
    previous_modules = {name: sys.modules.get(name) for name in module_names}
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("K_DPP_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
        patch.setattr("dotenv.load_dotenv", lambda *_args, **_kwargs: False)
        patch.setattr("tempfile.tempdir", str(db_path.parent))
        patch.syspath_prepend(str(BACKEND_ROOT))
        for name in module_names:
            sys.modules.pop(name, None)
        try:
            module = importlib.import_module("main")
            assert Path(module.__file__).resolve() == BACKEND_ROOT / "main.py"
            assert Path(module.database.engine.url.database) == db_path
            yield module
        finally:
            database = sys.modules.get("database")
            if database is not None:
                database.engine.dispose()
            for name, previous in previous_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous


class RecordingDb:
    def __init__(self) -> None:
        self.saved = []
        self.committed = False

    def add(self, record) -> None:
        self.saved.append(record)

    def commit(self) -> None:
        self.committed = True


@pytest.fixture
def scan_db(backend_main, monkeypatch):
    names = {"cotton": "면", "polyester": "폴리에스터"}
    monkeypatch.setattr(
        backend_main,
        "find_material",
        lambda _db, name: SimpleNamespace(name_en=name, name_ko=names[name]),
    )
    return RecordingDb()


def make_upload(content_type="image/jpeg"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    buffer.seek(0)
    headers = Headers({"content-type": content_type}) if content_type else Headers()
    return UploadFile(filename="label.jpg", file=buffer, headers=headers)


def test_backend_imports_the_repository_ai_modules(backend_main) -> None:
    assert backend_main.AI_MODULE_PATH == REPOSITORY_ROOT / "AI" / "kdpp_ai_ocr_integrated"
    assert backend_main.run_ocr is ocr_text.run_ocr_with_metadata
    assert backend_main.parse_label is parse_label


def test_runtime_wiring_check_requires_metadata_service(backend_main, monkeypatch, capsys) -> None:
    check = importlib.import_module("check_ai_wiring")
    assert check.main() == 0
    capsys.readouterr()
    monkeypatch.setattr(backend_main, "analyze_ocr_result", None)
    assert check.main() == 1
    assert "analyze_ocr_result" in capsys.readouterr().err


def test_scan_label_uses_ai_parser_and_returns_analysis_response(backend_main, scan_db) -> None:
    response = backend_main.scan_label(
        image=make_upload(),
        raw_ocr_text="COTTON 80% POLYESTER 20%\nDO NOT WASH\nDO NOT BLEACH",
        db=scan_db,
        current_user=SimpleNamespace(id=1),
    )

    assert response["status"] == "success"
    assert response["ai_success"] is True
    assert response["analysis_failure_reason"] is None
    assert response["materials"] == {"cotton": 80, "polyester": 20}
    assert response["material_details"] == [
        {
            "original_name": "cotton", "standard_name": "cotton",
            "display_name": "면", "ratio": 80, "is_supported": True,
        },
        {
            "original_name": "polyester", "standard_name": "polyester",
            "display_name": "폴리에스터", "ratio": 20, "is_supported": True,
        },
    ]
    assert response["care_instruction"] == "물세탁 금지; 표백 금지"
    assert response["title"] == "스캔한 의류"
    assert response["category"] == "상의"
    # Carbon calculation and history writes belong to /api/carbon/calculate.
    assert "carbon_footprint" not in response
    assert "saved_result_id" not in response
    assert scan_db.committed is False
    assert scan_db.saved == []


def test_scan_rejects_unconfirmed_outer_without_using_lining(backend_main, scan_db) -> None:
    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(), raw_ocr_text="OUTER COTTON 95%\nLINING COTTON 100%",
            db=scan_db, current_user=SimpleNamespace(id=1),
        )
    assert raised.value.status_code == 422
    assert raised.value.detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert not raised.value.detail.get("partial_materials")
    assert not raised.value.detail.get("materials")
    assert scan_db.saved == []
    assert scan_db.committed is False


def test_scan_label_runs_ocr_then_ai_parser(backend_main, scan_db, monkeypatch) -> None:
    image = make_upload()
    expected_bytes = image.file.getvalue()
    ocr_paths = []

    def fake_ocr(image_path, credential_path=None):
        path = Path(image_path)
        assert path.read_bytes() == expected_bytes
        ocr_paths.append(path)
        return "COTTON 100%\nDO NOT BLEACH"

    monkeypatch.setattr(backend_main, "run_ocr", fake_ocr)
    response = backend_main.scan_label(
        image=image, raw_ocr_text=None, db=scan_db, current_user=SimpleNamespace(id=1),
    )

    assert response["materials"] == {"cotton": 100}
    assert response["care_instruction"] == "표백 금지"
    assert response["ai_success"] is True
    assert len(ocr_paths) == 1
    assert not ocr_paths[0].exists()
    assert scan_db.saved == []
    assert scan_db.committed is False


def test_scan_rejects_conflicting_ocr_candidates_without_saving(
    backend_main, scan_db, monkeypatch,
) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(
        ocr_text, "_run_google_ocr",
        lambda *_args, **_kwargs: ocr_text.OcrPayload("COTTON 100%", "POLYESTER 100%"),
    )

    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(), raw_ocr_text=None, db=scan_db,
            current_user=SimpleNamespace(id=1),
        )

    assert raised.value.status_code == 422
    assert raised.value.detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert "generic:ambiguous_composition_candidates" in raised.value.detail["warnings"]
    assert not INTERNAL_KEYS & raised.value.detail.keys()
    assert scan_db.saved == []
    assert scan_db.committed is False


def test_scan_returns_successful_ocr_materials_without_internal_metadata(
    backend_main, scan_db, monkeypatch,
) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(
        ocr_text, "_run_google_ocr",
        lambda *_args, **_kwargs: ocr_text.OcrPayload(
            "COTTON 80% POLYESTER 20%", "POLYESTER 20% COTTON 80%",
        ),
    )
    response = backend_main.scan_label(
        image=make_upload(), raw_ocr_text=None, db=scan_db,
        current_user=SimpleNamespace(id=1),
    )

    assert response["materials"] == {"cotton": 80, "polyester": 20}
    assert response["ai_success"] is True
    assert response["warnings"] == []
    assert not INTERNAL_KEYS & response.keys()
    assert scan_db.saved == []
    assert scan_db.committed is False


def test_scan_reports_available_review_without_exposing_options_or_saving(
    backend_main, scan_db, monkeypatch,
) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(
        ocr_text, "_run_google_ocr",
        lambda *_args, **_kwargs: ocr_text.OcrPayload(
            "MATERIAL\nCOTTON 80%\nPOLYESTER 20%\nCUSTOMFIBER 60%\nPOLYESTER 40%",
            layout_words=(OcrWord("MATERIAL", 0, 0, 4, 1),),
        ),
    )
    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(), raw_ocr_text=None, db=scan_db,
            current_user=SimpleNamespace(id=1),
        )
    detail = raised.value.detail
    assert raised.value.status_code == 422 and detail["materials"] == {}
    assert "manual_composition_review_required:first_generic" in detail["warnings"]
    assert not INTERNAL_KEYS & detail.keys()
    assert scan_db.saved == [] and scan_db.committed is False


@pytest.mark.parametrize("ratio_row", ["100%", "100", "50"])
def test_scan_keeps_unpaired_ratio_warning_on_material_failure(
    backend_main, scan_db, monkeypatch, ratio_row,
) -> None:
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(
        ocr_text, "_run_google_ocr",
        lambda *_args, **_kwargs: ocr_text.OcrPayload(
            f"COTTON 100%\n{ratio_row}", "COTTON 100%",
        ),
    )
    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(), raw_ocr_text=None, db=scan_db,
            current_user=SimpleNamespace(id=1),
        )

    assert raised.value.status_code == 422
    detail = raised.value.detail
    assert detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert detail["materials"] == detail["partial_materials"] == {}
    assert "generic:unpaired_ratio_rows" in detail["warnings"]
    assert not INTERNAL_KEYS & detail.keys()
    assert scan_db.saved == []
    assert scan_db.committed is False


@pytest.mark.parametrize("content_type", [None, "text/plain"])
def test_scan_rejects_invalid_upload_even_with_raw_text(
    backend_main, scan_db, monkeypatch, content_type,
) -> None:
    monkeypatch.setattr(
        backend_main, "parse_label",
        lambda _text: pytest.fail("An invalid upload must be rejected before parsing"),
    )
    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(content_type), raw_ocr_text="COTTON 100%",
            db=scan_db, current_user=SimpleNamespace(id=1),
        )
    assert raised.value.status_code == 415
    assert raised.value.detail["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"
    assert scan_db.saved == []
    assert scan_db.committed is False


def test_scan_returns_material_failure_without_saving(backend_main, scan_db) -> None:
    with pytest.raises(HTTPException) as raised:
        backend_main.scan_label(
            image=make_upload(), raw_ocr_text="COTTON 80%",
            db=scan_db, current_user=SimpleNamespace(id=1),
        )
    assert raised.value.status_code == 422
    assert raised.value.detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert raised.value.detail["ai_success"] is False
    assert scan_db.saved == []
    assert scan_db.committed is False
