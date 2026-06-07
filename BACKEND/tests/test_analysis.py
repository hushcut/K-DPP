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
    assert body["saved_result_id"] is not None


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

    analyze = client.post(
        "/analyze",
        json={
            "materials": {
                "cotton": 80,
                "polyester": 20,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    history = client.get(
        "/me/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = history.json()

    assert analyze.status_code == 200
    assert history.status_code == 200
    assert body["status"] == "success"
    assert body["user"]["id"] == user_id
    assert len(body["history"]) == 1
    assert body["history"][0]["user_id"] == user_id
    assert body["history"][0]["id"] == analyze.json()["saved_result_id"]


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
    assert body["saved_result_id"] is not None

    history = client.get("/me/history", headers=headers).json()["history"]
    assert history[0]["carbon_footprint_min"] == 0.83
    assert history[0]["carbon_footprint_max"] == 2.08
    assert history[0]["min_weight_grams"] == 100
    assert history[0]["max_weight_grams"] == 250


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


def test_scan_returns_materials_without_saving_carbon_result(client):
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "COTTON 80% POLYESTER 20%"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["materials"] == {"cotton": 80, "polyester": 20}
    assert "carbon_footprint" not in body
    assert "saved_result_id" not in body


def test_scan_requires_image_error_code(client):
    response = client.post("/api/scan")
    body = response.json()

    assert response.status_code == 422
    assert body["status"] == "error"
    assert body["error_code"] == "IMAGE_MISSING"


def test_scan_rejects_unsupported_image_type(client):
    response = client.post(
        "/api/scan",
        files={"image": ("label.txt", b"not-image", "text/plain")},
    )
    body = response.json()

    assert response.status_code == 415
    assert body["status"] == "error"
    assert body["error_code"] == "UNSUPPORTED_IMAGE_FORMAT"


def test_scan_material_failure_returns_partial_context(client):
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "wash cold do not bleach dry flat"},
    )
    body = response.json()

    assert response.status_code == 422
    assert body["status"] == "error"
    assert body["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert body["detail"]["error_code"] == "MATERIAL_EXTRACTION_FAILED"
    assert body["detail"]["partial_materials"] == {}
    assert "raw_ocr_preview" in body["detail"]
