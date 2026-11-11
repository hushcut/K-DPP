"""Regression checks for the backend path that consumes AI OCR parsing."""

from __future__ import annotations

from io import BytesIO
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
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
    # The scan marks a material supported only when the active V2 policy has a factor for it;
    # None means "no single active policy", so support falls back to catalog membership as before.
    monkeypatch.setattr(backend_main, "active_profile_material_ids", lambda _db: None)
    return RecordingDb()


def make_upload(content_type="image/jpeg"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    buffer.seek(0)
    headers = Headers({"content-type": content_type}) if content_type else Headers()
    return UploadFile(filename="label.jpg", file=buffer, headers=headers)


@pytest.fixture
def scan_image_client(backend_main, scan_db, monkeypatch, tmp_path):
    # These error paths must stop before DB access. Use the real HTTP route,
    # middleware and exception handler without entering the DB-checking lifespan.
    def forbid_db(*_args, **_kwargs):
        pytest.fail("image input errors must not connect to a database")

    monkeypatch.setattr(backend_main.database.engine, "connect", forbid_db)
    monkeypatch.setattr(backend_main.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(backend_main, "_vision_scan_counts", {})
    monkeypatch.setattr(backend_main, "SCAN_DAILY_MAX", None)
    monkeypatch.setattr(backend_main, "SCAN_USER_DAILY_MAX", 20)
    monkeypatch.setattr(backend_main.app, "dependency_overrides", {
        backend_main.get_db: lambda: scan_db,
        backend_main.get_current_user: lambda: SimpleNamespace(id=1),
    })
    client = TestClient(backend_main.app)
    yield client
    client.close()
    assert scan_db.saved == [] and not scan_db.committed
    assert list(tmp_path.iterdir()) == [], "failed uploads must remove their temporary files"


def damaged_scan_image(image_format, truncated=False):
    image = Image.new("RGB", (64, 40), "white")
    exif = b"Exif\0\0BAD!0000"
    if truncated:
        exif = Image.Exif()
        exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format=image_format, exif=exif, dpi=(72, 72))
    return buffer.getvalue()[:-8] if truncated else buffer.getvalue()


@pytest.mark.parametrize("image_format,truncated", [("JPEG", False), ("PNG", False), ("WEBP", False), ("JPEG", True)])
def test_damaged_image_is_400_before_vision(backend_main, scan_image_client, monkeypatch, image_format, truncated):
    def forbid_vision(*_args, **_kwargs):
        pytest.fail("damaged images must stop before Vision")

    monkeypatch.setattr(ocr_text, "_get_vision_client", forbid_vision)
    monkeypatch.setattr(ocr_text, "_run_google_ocr", forbid_vision)
    content_type = "image/" + image_format.lower()
    response = scan_image_client.post("/api/scan", files={
        "image": ("label", damaged_scan_image(image_format, truncated), content_type),
    })
    body = response.json()
    assert response.status_code == 400
    assert body["status"] == "error"
    assert body["error_code"] == body["detail"]["error_code"] == "INVALID_IMAGE"
    assert "다른 사진" in body["message"]
    assert not any(key in body["detail"] for key in INTERNAL_KEYS)
    # Classification does not change the existing reservation policy.
    assert sum(sum(counts.values()) for counts in backend_main._vision_scan_counts.values()) == 1


def test_unreadable_image_has_matching_400_response_and_photo_log(scan_image_client, monkeypatch, capsys):
    def forbid_vision(*_args, **_kwargs):
        pytest.fail("unreadable images must stop before Vision")

    monkeypatch.setattr(ocr_text, "_get_vision_client", forbid_vision)
    monkeypatch.setattr(ocr_text, "_run_google_ocr", forbid_vision)
    response = scan_image_client.post("/api/scan", files={"image": ("label.jpg", b"not an image", "image/jpeg")})
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_IMAGE"
    [line] = [line for line in capsys.readouterr().err.splitlines() if line.startswith("[scan] 사진 ")]
    assert "결과=400" in line and "실제형식=-" in line and "열기=UnidentifiedImageError" in line


@pytest.mark.parametrize("error_name,status,code", [
    ("InvalidImageError", 400, "INVALID_IMAGE"),
    ("ImageTooLargeError", 413, "PAYLOAD_TOO_LARGE"),
    ("UnsupportedImageError", 415, "UNSUPPORTED_IMAGE_FORMAT"),
    ("OcrTimeoutError", 504, "OCR_TIMEOUT"),
    ("OcrTotalTimeoutError", 504, "OCR_TIMEOUT"),
    ("OcrConfigurationError", 502, "OCR_FAILED"),
    ("OcrQuotaExceededError", 502, "OCR_FAILED"),
    ("OcrUnavailableError", 502, "OCR_FAILED"),
    ("OcrServiceError", 502, "OCR_FAILED"),
    ("RuntimeError", 502, "OCR_FAILED"),
])
def test_ocr_exception_families_have_distinct_safe_http_responses(
    backend_main, scan_image_client, monkeypatch, error_name, status, code,
):
    def fail_ocr(*_args, **_kwargs):
        error_type = RuntimeError if error_name == "RuntimeError" else getattr(ocr_text, error_name)
        raise error_type("private-diagnostic-marker")

    monkeypatch.setattr(backend_main, "run_ocr", fail_ocr)
    response = scan_image_client.post("/api/scan", files={"image": ("label.jpg", b"input", "image/jpeg")})
    assert response.status_code == status
    assert response.json()["error_code"] == code
    assert "private-diagnostic-marker" not in response.text


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
    assert response["warnings"] == ["composition_part:unidentified"]
    assert not INTERNAL_KEYS & response.keys()
    assert scan_db.saved == []
    assert scan_db.committed is False


@pytest.mark.parametrize("text,code,status_code", [
    ("OUTER COTTON 100%", "composition_part:outer", 200),
    ("겉감2 면 100%", "composition_part:outer_2", 200),
    ("LINING POLYESTER 100%", "composition_part:lining", 200),
    ("COTTON 100%", "composition_part:unidentified", 200),
    ("OUTER COTTON 95%\nLINING POLYESTER 100%",
     "composition_action:retake_composition_region", 422),
])
def test_scan_passes_public_guidance_without_internal_metadata_or_saving(
    backend_main, scan_db, monkeypatch, text, code, status_code,
) -> None:
    reading = ocr_text.OcrResult(text, ocr_text.OcrMetadata(
        source="original", confidence="medium", candidate_count=1,
        image_format="JPEG", width=4, height=4,
        attempts=(ocr_text.OcrAttempt("original", "success", 0, False),), attempt_count=1,
    ))
    monkeypatch.setattr(backend_main, "run_ocr", lambda *_args, **_kwargs: reading)
    arguments = dict(
        image=make_upload(), raw_ocr_text=None, db=scan_db,
        current_user=SimpleNamespace(id=1),
    )
    if status_code == 422:
        with pytest.raises(HTTPException) as raised:
            backend_main.scan_label(**arguments)
        assert raised.value.status_code == 422
        payload = raised.value.detail
        assert payload["materials"] == {}
        assert not any(warning.startswith("composition_part:") for warning in payload["warnings"])
    else:
        payload = backend_main.scan_label(**arguments)
        assert payload["materials"]
    assert code in payload["warnings"]
    assert not INTERNAL_KEYS & payload.keys()
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
