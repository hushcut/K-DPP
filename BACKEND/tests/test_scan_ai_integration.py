"""사진 스캔이 새 AI(run_ocr_with_metadata → analyze_ocr_result)를 거치는 길(DECISIONS 199·200·210·211).

Vision 은 부르지 않는다. AI 의 Vision 클라이언트·호출 함수만 바꿔 끼워, AI 의 후보 판정·파서·응답
계약은 실제 코드 그대로 돈다. 인증은 하루 상한 테스트처럼 get_current_user 를 바꿔 끼워 건너뛴다.
"""

import io
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


def test_two_column_label_is_422_but_prefills_direct_input(client, vision):
    # 겉감·안감 두 칸 표: 줄 순서 판독은 '면 100%' 를 안감에, 좌표 판독은 겉감에 붙인다. AI 는 두 부위를
    # 다 버려 확정하지 않지만, 조성은 같으니 직접 입력 칸은 채운다(DECISIONS 270 — 실제 사진 재현과 같은 꼴).
    vision.answer("혼용율\n겉감\n안감\n면 100%", "혼용율\n겉감 면 100 %\n안감")

    response = scan(client)
    detail = response.json()["detail"]

    assert response.status_code == 422
    assert detail["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert detail["materials"] == {}
    assert detail["partial_materials"] == {"cotton": 100}
    assert detail["ai_success"] is False
    assert main.PREFILL_MATERIALS_KEY not in response.text
    assert not any(key in detail for key in INTERNAL_KEYS)


@pytest.mark.parametrize(
    "reparsed",
    [
        {"status": "failed", "materials": {"cotton": 100}, "selected_part": "outer"},
        {"status": "success", "materials": {"cotton": 60}, "selected_part": "outer"},
    ],
)
def test_prefill_needs_a_confirmed_complete_reparse(client, vision, monkeypatch, reparsed):
    # 다시 읽은 결과도 파서가 성공하고 합계가 100 일 때만 채운다 — 빠진 소재를 사용자가 못 볼 수 있다.
    # 사진 판정은 AI 의 파서를 직접 쓰므로, 바꿔 끼운 main.parse_label 은 다시 읽기에만 닿는다.
    vision.answer("혼용율\n겉감\n안감\n면 100%", "혼용율\n겉감 면 100 %\n안감")
    monkeypatch.setattr(main, "parse_label", lambda text: reparsed)

    response = scan(client)

    assert response.status_code == 422
    assert response.json()["detail"]["partial_materials"] == {}


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
