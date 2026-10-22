"""사진 스캔이 새 AI(run_ocr_with_metadata → analyze_ocr_result)를 거치는 길(DECISIONS 199·200·210·211).

Vision 은 부르지 않는다. AI 의 Vision 클라이언트·호출 함수만 바꿔 끼워, AI 의 후보 판정·파서·응답
계약은 실제 코드 그대로 돈다. 인증은 하루 상한 테스트처럼 get_current_user 를 바꿔 끼워 건너뛴다.
"""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import main
from apps.text import ocr_text


# 응답 공개 범위는 warnings 뿐이다(DECISIONS 210) — 이 셋은 앱으로 나가면 안 된다.
INTERNAL_KEYS = ("ocr", "confidence", "parse_evidence")


def jpeg_bytes() -> bytes:
    # AI 는 실제 이미지인지 열어 보므로 진짜 JPEG 이어야 한다.
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture()
def vision(client, monkeypatch):
    """가짜 Vision: 부른 횟수를 모은다. answer(text, layout) 로 돌려줄 글자를, fail(exc) 로 예외를 정한다."""
    state = SimpleNamespace(calls=0, payload=None, error=None)

    def fake_google_ocr(*_args, **_kwargs):
        state.calls += 1
        if state.error is not None:
            raise state.error
        return state.payload

    def answer(text, layout_text=""):
        state.payload = ocr_text.OcrPayload(text, layout_text)

    def fail(error):
        state.error = error

    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_google_ocr)
    state.answer = answer
    state.fail = fail
    yield state
    main.app.dependency_overrides.pop(main.get_current_user, None)


def scan(client, **data):
    main.app.dependency_overrides[main.get_current_user] = lambda: SimpleNamespace(id=1)
    return client.post(
        "/api/scan", files={"image": ("label.jpg", jpeg_bytes(), "image/jpeg")}, data=data,
    )


def counted_scans() -> int:
    return sum(sum(counts.values()) for counts in main._vision_scan_counts.values())


def test_photo_scan_returns_materials_and_warnings_only(client, vision):
    vision.answer("COTTON 80% POLYESTER 20%", "POLYESTER 20% COTTON 80%")

    response = scan(client)
    body = response.json()

    assert response.status_code == 200
    assert body["materials"] == {"cotton": 80, "polyester": 20}
    assert body["ai_success"] is True
    # 겉감·안감 표기가 없는 성공이라 AI 가 부위 미확정 안내만 붙인다(R4 — 소재 인식 실패가 아님).
    assert body["warnings"] == ["composition_part:unidentified"]
    assert not any(key in body for key in INTERNAL_KEYS)
    assert counted_scans() == 1


def test_conflicting_ocr_candidates_are_422_without_internal_metadata(client, vision):
    # 원본과 좌표 순서 후보가 서로 다른 조성을 읽으면 AI 는 어느 쪽도 확정하지 않는다.
    vision.answer("COTTON 100%", "POLYESTER 100%")

    response = scan(client)
    detail = response.json()["detail"]

    assert response.status_code == 422
    assert detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert detail["materials"] == detail["partial_materials"] == {}
    assert detail["ai_success"] is False
    assert detail["parser_error_code"] == "ambiguous_composition"
    assert "generic:ambiguous_composition_candidates" in detail["warnings"]
    assert not any(key in detail for key in INTERNAL_KEYS)
    # Vision 은 이미 불렀으니 세고 되돌리지 않는다(DECISIONS 164).
    assert counted_scans() == 1


def test_unpaired_ratio_row_is_422_not_a_confirmed_material(client, vision):
    # 짝 없는 비율 줄('50')이 있으면 COTTON 100% 도 확정하지 않는다.
    vision.answer("COTTON 100%\n50", "COTTON 100%")

    response = scan(client)
    detail = response.json()["detail"]

    assert response.status_code == 422
    assert detail["materials"] == detail["partial_materials"] == {}
    assert "generic:unpaired_ratio_rows" in detail["warnings"]


@pytest.mark.parametrize("error_name", ["OcrTimeoutError", "OcrTotalTimeoutError"])
def test_vision_timeout_is_504_and_counted(client, vision, error_name):
    vision.fail(getattr(ocr_text, error_name)("C:/secret/key.json 응답 시간 초과"))

    response = scan(client)

    assert response.status_code == 504
    assert response.json()["error_code"] == "OCR_TIMEOUT"
    assert "secret" not in response.text and "key.json" not in response.text
    assert counted_scans() == 1


@pytest.mark.parametrize(
    "error_name",
    ["OcrConfigurationError", "OcrQuotaExceededError", "OcrUnavailableError", "OcrServiceError"],
)
def test_other_vision_failures_stay_502(client, vision, error_name):
    # 503 은 서버 전체 하루 상한·AI 모듈 없음이 이미 쓰므로, 일시 장애도 502 다(DECISIONS 211).
    vision.fail(getattr(ocr_text, error_name)("C:/secret/key.json 자격 증명 오류"))

    response = scan(client)

    assert response.status_code == 502
    assert response.json()["error_code"] == "OCR_FAILED"
    assert "secret" not in response.text and "key.json" not in response.text
    assert counted_scans() == 1


def test_missing_analyzer_is_503_before_vision_and_not_counted(client, vision, monkeypatch):
    # 분석 함수가 없으면 Vision 을 불러도 끝까지 갈 수 없으므로, 부르기(세기) 전에 503 이다.
    monkeypatch.setattr(main, "analyze_ocr_result", None)
    vision.answer("COTTON 100%")

    response = scan(client)

    assert response.status_code == 503
    assert response.json()["error_code"] == "AI_MODULE_FAILED"
    assert vision.calls == 0
    assert counted_scans() == 0


def test_text_scan_also_returns_warnings_list(client, vision):
    response = scan(client, raw_ocr_text="COTTON 100%")

    assert response.status_code == 200
    assert response.json()["warnings"] == []
    assert vision.calls == 0


def test_parser_failure_is_422_even_with_materials(client, vision, monkeypatch):
    # 소재를 확정하는 기준은 파서의 status 다 — 합계가 100 이어도 실패면 확정 소재로 내보내지 않는다.
    monkeypatch.setattr(
        main,
        "parse_label",
        lambda text: {"status": "failed", "materials": {"cotton": 100}, "raw_ocr_preview": text},
    )

    response = scan(client, raw_ocr_text="COTTON 100%")

    assert response.status_code == 422
    assert response.json()["detail"]["materials"] == {}


def test_parser_success_with_incomplete_total_is_422_with_prefill(client, vision, monkeypatch):
    # 파서가 성공이라 해도 합계가 100 이 아니면 확정하지 않는다. 직접 입력 폼은 partial_materials 로 채운다.
    monkeypatch.setattr(
        main,
        "parse_label",
        lambda text: {"status": "success", "materials": {"cotton": 60}, "raw_ocr_preview": text},
    )

    response = scan(client, raw_ocr_text="COTTON 60%")
    detail = response.json()["detail"]

    assert response.status_code == 422
    assert detail["materials"] == {}
    assert detail["partial_materials"] == {"cotton": 60}


# --- 방향 값이 붙은 사진(DECISIONS 273) ---------------------------------------------------------
# 폰 앱의 앨범 경로(image_picker)는 화소를 눕힌 채 방향 값 6 을 붙인 JPEG 를 올린다. 서버가 바로 세워 AI 에 넘기고,
# 사진 스캔마다 파일 모양을 한 줄 남긴다(사진·글자·GPS 값은 없이).
GPS_LATITUDE = (37.0, 7.0, 12.3456)


def sideways_bytes(image_format: str = "JPEG") -> bytes:
    """가로 8 × 세로 4 화소에 방향 값 6(시계 방향 90° 로 보여야 함)과 GPS 를 붙인 사진."""
    exif = Image.Exif()
    exif[274] = 6
    exif[0x8825] = {1: "N", 2: GPS_LATITUDE}
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4), "white").save(buffer, format=image_format, exif=exif)
    return buffer.getvalue()


@pytest.fixture()
def ocr_input(monkeypatch):
    """AI 가 실제로 받은 사진 바이트를 모은다(run_ocr 는 그대로 돈다)."""
    seen = []
    original = main.run_ocr

    def spy(path, **kwargs):
        seen.append(Path(path).read_bytes())
        return original(path, **kwargs)

    monkeypatch.setattr(main, "run_ocr", spy)
    return seen


def scan_file(client, content: bytes, content_type: str = "image/jpeg"):
    main.app.dependency_overrides[main.get_current_user] = lambda: SimpleNamespace(id=1)
    return client.post("/api/scan", files={"image": ("label", content, content_type)})


def scan_log_lines(capsys) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.startswith("[scan] 사진 ")]


@pytest.mark.parametrize(("image_format", "content_type"), [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_sideways_photo_is_uprighted_without_exif_before_ocr(client, vision, ocr_input, image_format, content_type):
    vision.answer("COTTON 100%")

    response = scan_file(client, sideways_bytes(image_format), content_type)

    assert response.status_code == 200
    with Image.open(io.BytesIO(ocr_input[0])) as received:
        # 방향 값대로 돌린 세로 사진이고, 방향 값·GPS 를 포함한 EXIF 는 남지 않는다.
        assert (received.format, received.size) == ("JPEG", (4, 8))
        assert len(received.getexif()) == 0


def test_upright_photo_reaches_ocr_unchanged(client, vision, ocr_input):
    vision.answer("COTTON 100%")
    content = jpeg_bytes()

    response = scan_file(client, content)

    assert response.status_code == 200
    assert ocr_input == [content]


def test_scan_log_line_has_file_shape_but_no_gps_value(client, vision, capsys):
    vision.answer("COTTON 100%")
    content = sideways_bytes()

    scan_file(client, content)
    [line] = scan_log_lines(capsys)

    for field in (
        "결과=200", "보낸형식=image/jpeg", "실제형식=JPEG", f"바이트={len(content)}", "크기=8x4", "방향=6",
        "바로세움=예", "EXIF=있음", "GPS=있음", "색=RGB", "AI판정=success", "소재칸=1", "합계=100",
        'warnings=["composition_part:unidentified"]',
    ):
        assert field in line
    assert "12.3456" not in line and "37.0" not in line


def test_scan_log_line_records_422_codes(client, vision, capsys):
    vision.answer("혼용율\n겉감\n안감\n면 100%", "혼용율\n겉감 면 100 %\n안감")

    response = scan(client)
    [line] = scan_log_lines(capsys)

    assert response.status_code == 422
    assert "결과=422" in line and "방향=없음" in line and "바로세움=아니오" in line and "GPS=없음" in line
    assert 'parser_error_code="composition_not_found"' in line
    assert "AI판정=failed" in line and "소재칸=0" in line
    # 라벨 글자는 남기지 않는다.
    assert "혼용율" not in line and "면 100" not in line


def test_unreadable_photo_is_logged_and_left_to_ai(client, vision, capsys):
    response = scan_file(client, b"not an image")
    [line] = scan_log_lines(capsys)

    # 서버는 열지 못한 사진을 바꾸지 않고 넘기며, 오류는 지금처럼 AI 의 형식 검사에서 난다.
    assert response.status_code == 502
    assert "결과=502" in line and "실제형식=-" in line and "열기=UnidentifiedImageError" in line
    assert vision.calls == 0


def test_text_scan_writes_no_photo_log_line(client, vision, capsys):
    response = scan(client, raw_ocr_text="COTTON 100%")

    assert response.status_code == 200
    assert scan_log_lines(capsys) == []
