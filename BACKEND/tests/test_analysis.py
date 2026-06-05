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
