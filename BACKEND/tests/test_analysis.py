from pathlib import Path

import pytest

import main
from apps.text import ocr_text


def test_analyze_calculates_cotton_polyester(client):
    response = client.post(
        "/analyze",
        json={
            "materials": {
                "cotton": 80,
                "polyester": 20,
            },
            "raw_ocr_text": "COTTON 80% POLYESTER 20%",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["materials"] == {"cotton": 80, "polyester": 20}
    assert body["carbon_footprint"] == 8.54
    assert body["unit"] == "kg CO2eq"
    # /analyze는 계산 전용으로 바뀌어 더 이상 이력을 저장하지 않습니다.
    assert body["saved_result_id"] is None


def test_analyze_returns_400_for_unknown_material(client):
    response = client.post(
        "/analyze",
        json={
            "materials": {
                "unknown_fiber": 100,
            },
        },
    )

    body = response.json()

    assert response.status_code == 400
    assert body["status"] == "error"
    assert body["error_code"] == "MATERIAL_NOT_FOUND"
    assert body["detail"]["unknown_materials"] == ["unknown_fiber"]


def test_analyze_returns_400_when_ratio_total_is_not_100(client):
    response = client.post(
        "/analyze",
        json={
            "materials": {
                "cotton": 80,
                "polyester": 10,
            },
        },
    )

    body = response.json()

    assert response.status_code == 400
    assert body["status"] == "error"
    assert body["error_code"] == "MATERIAL_RATIO_INVALID"
    assert "90" in body["message"]


def test_authenticated_analyze_is_visible_in_my_history(client):
    signup = client.post(
        "/auth/signup",
        json={
            "email": "history@example.com",
            "password": "password123",
            "nickname": "history-user",
        },
    )
    user_id = signup.json()["user"]["id"]

    login = client.post(
        "/auth/login",
        json={
            "email": "history@example.com",
            "password": "password123",
        },
    )
    token = login.json()["access_token"]

    calculate = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 80, "polyester": 20},
            "weight_grams": 200,
            "save_history": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # /analyze는 계산 전용이라 이력에 남지 않아야 합니다.
    analyze = client.post(
        "/analyze",
        json={"materials": {"cotton": 80, "polyester": 20}},
        headers={"Authorization": f"Bearer {token}"},
    )

    history = client.get(
        "/me/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = history.json()

    assert calculate.status_code == 200
    assert analyze.status_code == 200
    assert history.status_code == 200
    assert body["status"] == "success"
    assert body["user"]["id"] == user_id
    assert len(body["history"]) == 1
    assert body["history"][0]["user_id"] == user_id
    # 이력의 created_at은 UTC 오프셋을 포함해야 합니다(시간대 오해 방지).
    assert body["history"][0]["created_at"].endswith("+00:00")


def test_my_history_requires_login(client):
    response = client.get("/me/history")

    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_history_requires_login(client):
    response = client.get("/history")

    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_carbon_range_uses_db_factor_and_weight_range(client):
    client.post(
        "/auth/signup",
        json={
            "email": "carbon@example.com",
            "password": "password123",
            "nickname": "carbon-user",
        },
    )
    login = client.post(
        "/auth/login",
        json={
            "email": "carbon@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 100},
            "min_weight_grams": 100,
            "max_weight_grams": 250,
        },
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 200
    assert body["carbon_factor"] == 8.3
    assert body["carbon_footprint_min"] == 0.83
    assert body["carbon_footprint_max"] == 2.08
    assert body["carbon_footprint"] == 1.46
    assert body["average_carbon_footprint"] == 1.46
    assert body["source"] == "backend"
    assert body["calculation_scope"] == "material_production_estimate"
    assert "development estimates" in body["calculation_source"]
    assert "개발용 추정값" in body["calculation_note"]
    assert body["weight_source"] == "range"
    assert body["emission_factors"] == [
        {
            "input_name": "cotton",
            "standard_name": "cotton",
            "display_name": "면",
            "ratio": 100.0,
            "carbon_factor": 8.3,
            "unit": "kg CO2eq/kg textile",
            "source": "K-DPP backend material carbon factor table (development estimates)",
        }
    ]
    assert body["saved_result_id"] is not None

    history = client.get("/me/history", headers=headers).json()["history"]
    assert history[0]["carbon_footprint_min"] == 0.83
    assert history[0]["carbon_footprint_max"] == 2.08
    assert history[0]["min_weight_grams"] == 100
    assert history[0]["max_weight_grams"] == 250


def test_carbon_range_prefers_direct_weight(client):
    client.post(
        "/auth/signup",
        json={
            "email": "direct-weight@example.com",
            "password": "password123",
            "nickname": "direct-weight-user",
        },
    )
    login = client.post(
        "/auth/login",
        json={
            "email": "direct-weight@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 100},
            "min_weight_grams": 100,
            "max_weight_grams": 250,
            "weight_grams": 300,
            "clothing_type": "반팔",
            "category": "상의",
        },
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 200
    assert body["weight_source"] == "direct"
    assert body["min_weight_grams"] == 300
    assert body["max_weight_grams"] == 300
    assert body["weight_grams"] == 300
    assert body["carbon_footprint_min"] == 2.49
    assert body["carbon_footprint_max"] == 2.49
    assert body["carbon_footprint"] == 2.49
    assert body["clothing_type"] == "반팔"
    assert body["category"] == "상의"


def test_carbon_range_requires_weight_input(client):
    client.post(
        "/auth/signup",
        json={
            "email": "missing-weight@example.com",
            "password": "password123",
            "nickname": "missing-weight-user",
        },
    )
    login = client.post(
        "/auth/login",
        json={
            "email": "missing-weight@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/carbon/calculate",
        json={"materials": {"cotton": 100}},
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 400
    assert body["error_code"] == "WEIGHT_MISSING"


def test_carbon_range_requires_login(client):
    response = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 100},
            "min_weight_grams": 100,
            "max_weight_grams": 250,
        },
    )

    assert response.status_code == 401


def _login_token(client, email="scan-user@example.com"):
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "scan-user"},
    )
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    return login.json()["access_token"]


def test_scan_requires_login(client):
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "COTTON 80% POLYESTER 20%"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_REQUIRED"


def test_scan_returns_materials_without_saving_carbon_result(client):
    token = _login_token(client)
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "COTTON 80% POLYESTER 20%"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["materials"] == {"cotton": 80, "polyester": 20}
    assert body["ai_success"] is True
    assert body["analysis_failure_reason"] is None
    assert body["clothing"] == {
        "name": "스캔한 의류",
        "category": "상의",
    }
    assert body["material_details"] == [
        {
            "original_name": "cotton",
            "standard_name": "cotton",
            "display_name": "면",
            "ratio": 80,
            "is_supported": True,
        },
        {
            "original_name": "polyester",
            "standard_name": "polyester",
            "display_name": "폴리에스터",
            "ratio": 20,
            "is_supported": True,
        },
    ]
    assert "raw_ocr_preview" in body
    assert "carbon_footprint" not in body
    assert "saved_result_id" not in body


def test_scan_requires_image_error_code(client):
    token = _login_token(client)
    response = client.post(
        "/api/scan", headers={"Authorization": f"Bearer {token}"}
    )
    body = response.json()

    assert response.status_code == 422
    assert body["status"] == "error"
    assert body["error_code"] == "IMAGE_MISSING"


def test_scan_rejects_unsupported_image_type(client):
    token = _login_token(client)
    response = client.post(
        "/api/scan",
        files={"image": ("label.txt", b"not-image", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()

    assert response.status_code == 415
    assert body["status"] == "error"
    assert body["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"


@pytest.mark.parametrize(
    ("raw_text", "expected_care", "expected_preview"),
    [
        (
            "wash cold do not bleach dry flat",
            "표백 금지; 찬물 기계세탁; 평평하게 뉘어서 건조",
            "wash cold do not bleach dry flat",
        ),
        ("DO NOT BLEACH", "표백 금지", "DO NOT BLEACH"),
        (
            "COTTON 60%\nDO NOT BLEACH",
            "표백 금지",
            "COTTON 60% DO NOT BLEACH",
        ),
    ],
)
def test_scan_material_failure_returns_partial_context(
    client, raw_text, expected_care, expected_preview
):
    token = _login_token(client)
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": raw_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()

    assert response.status_code == 422
    assert body["status"] == "error"
    assert body["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert body["detail"]["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    # 프론트 직접 입력 폼이 읽는 필드입니다. 이 네 개가 계약이며,
    # AI 브랜치를 머지하면서 detail을 줄이면 폼 프리필이 조용히 사라집니다.
    assert body["detail"]["materials"] == {}
    assert body["detail"]["partial_materials"] == {}
    assert body["detail"]["ai_success"] is False
    assert body["detail"]["care_instruction"] == expected_care
    assert body["detail"]["raw_ocr_preview"] == expected_preview
    assert "care_instruction" not in body


@pytest.mark.parametrize(
    ("care_fields", "expected_care"),
    [
        ({"care_text": "손세탁; 표백 금지"}, "손세탁; 표백 금지"),
        ({"care_instruction": "손세탁; 표백 금지"}, "손세탁; 표백 금지"),
        ({"care_text": "", "care_instruction": "표백 금지"}, "표백 금지"),
        (
            {"care_text": "", "care_instruction": ""},
            "라벨 표기법에 맞춰 관리하세요.",
        ),
    ],
)
def test_scan_accepts_either_care_key_from_parser(
    client, monkeypatch, care_fields, expected_care
):
    """AI 파서 버전에 따라 care_text/care_instruction 중 하나만 온다."""
    token = _login_token(client)

    monkeypatch.setattr(
        main,
        "parse_label",
        lambda text: {
            "materials": {"cotton": 100},
            "raw_ocr_preview": "COTTON 100%",
            **care_fields,
        },
    )

    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "COTTON 100%"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["materials"] == {"cotton": 100}
    assert body["care_instruction"] == expected_care
    assert body["raw_ocr_preview"] == "COTTON 100%"
    assert "care_text" not in body


@pytest.mark.parametrize(
    ("care_fields", "expected_care"),
    [
        ({"care_text": "손세탁; 표백 금지"}, "손세탁; 표백 금지"),
        ({"care_instruction": "손세탁; 표백 금지"}, "손세탁; 표백 금지"),
        ({"care_text": "", "care_instruction": "표백 금지"}, "표백 금지"),
        (
            {"care_text": "", "care_instruction": ""},
            "라벨 표기법에 맞춰 관리하세요.",
        ),
    ],
)
def test_scan_material_failure_keeps_parser_care_instruction(
    client, monkeypatch, care_fields, expected_care
):
    token = _login_token(client)

    monkeypatch.setattr(
        main,
        "parse_label",
        lambda text: {
            "materials": {},
            "raw_ocr_preview": "CARE ONLY",
            **care_fields,
        },
    )

    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "CARE ONLY"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert body["detail"]["care_instruction"] == expected_care
    assert body["detail"]["materials"] == {}
    assert body["detail"]["partial_materials"] == {}
    assert body["detail"]["ai_success"] is False
    assert body["detail"]["raw_ocr_preview"] == "CARE ONLY"
    assert "care_text" not in body["detail"]
    assert "care_instruction" not in body


@pytest.mark.parametrize(
    ("exception_type", "expected_status", "expected_code"),
    [
        (RuntimeError, 502, "OCR_FAILED"),
        (ocr_text.OcrServiceError, 502, "OCR_FAILED"),
        (ocr_text.OcrConfigurationError, 503, "OCR_NOT_CONFIGURED"),
        (ocr_text.OcrQuotaExceededError, 503, "OCR_QUOTA_EXCEEDED"),
        (ocr_text.OcrTimeoutError, 504, "OCR_TIMEOUT"),
        (ocr_text.OcrUnavailableError, 503, "OCR_SERVICE_UNAVAILABLE"),
    ],
)
def test_scan_ocr_failure_does_not_leak_exception_text(
    client, monkeypatch, tmp_path, exception_type, expected_status, expected_code
):
    """OCR 예외 원문에는 서버 경로·계정 식별자가 섞일 수 있어 응답에 넣지 않는다."""
    token = _login_token(client)
    uploaded_files = []
    monkeypatch.setattr(main.tempfile, "tempdir", str(tmp_path))

    def fake_ocr(image_path, credential_path=""):
        path = Path(image_path)
        exists = path.exists()
        uploaded_files.append((path, exists, path.read_bytes() if exists else None))
        raise exception_type(
            "C:/secret/key.json account-private@example.com private-provider-token"
        )

    monkeypatch.setattr(main, "run_ocr", fake_ocr)

    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert response.status_code == expected_status
    assert body["status"] == "error"
    assert body["error_code"] == expected_code
    assert body["detail"]["error_code"] == expected_code
    for sensitive_fragment in (
        "secret", "key.json", "account-private", "private-provider-token"
    ):
        assert sensitive_fragment not in response.text
    assert len(uploaded_files) == 1
    path, existed_during_ocr, content = uploaded_files[0]
    assert path.parent == tmp_path
    assert existed_during_ocr is True
    assert content == b"test-image"
    assert not path.exists()


@pytest.mark.parametrize(
    ("raw_text", "expected_care"),
    [
        ("COTTON 100%\nDO NOT BLEACH", "표백 금지"),
        ("COTTON 100%\nDO NOT TUMBLE DRY", "건조기 사용 금지"),
    ],
)
def test_scan_preserves_enhancement_parser_care_and_cleans_upload(
    client, monkeypatch, tmp_path, raw_text, expected_care
):
    """실제 enhancement 파서의 지침을 외부 계약으로 전달하며 OCR 업로드를 정리한다."""
    token = _login_token(client)
    uploaded_files = []
    monkeypatch.setattr(main.tempfile, "tempdir", str(tmp_path))

    def fake_ocr(image_path, credential_path=""):
        path = Path(image_path)
        exists = path.exists()
        uploaded_files.append((path, exists, path.read_bytes() if exists else None))
        return raw_text

    monkeypatch.setattr(main, "run_ocr", fake_ocr)
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["materials"] == {"cotton": 100}
    assert body["care_instruction"] == expected_care
    assert body["ai_success"] is True
    assert body["raw_ocr_preview"] == raw_text.replace("\n", " ")
    assert "care_text" not in body
    assert len(uploaded_files) == 1
    path, existed_during_ocr, content = uploaded_files[0]
    assert path.parent == tmp_path
    assert existed_during_ocr is True
    assert content == b"test-image"
    assert not path.exists()
