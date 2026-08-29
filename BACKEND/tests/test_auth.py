from datetime import timedelta

import database
import main


def _signup_and_login(client, email="session@example.com"):
    client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "password123",
            "nickname": "tester",
        },
    )
    return client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )


def test_signup_success(client):
    response = client.post(
        "/auth/signup",
        json={
            "email": "signup@example.com",
            "password": "password123",
            "nickname": "tester",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["user"]["email"] == "signup@example.com"
    assert body["user"]["nickname"] == "tester"


def test_signup_duplicate_email_fails(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "password123",
        "nickname": "tester",
    }

    first = client.post("/auth/signup", json=payload)
    second = client.post("/auth/signup", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["status"] == "error"


def test_login_success(client):
    client.post(
        "/auth/signup",
        json={
            "email": "login@example.com",
            "password": "password123",
            "nickname": "tester",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "password123",
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["user"]["email"] == "login@example.com"
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 24 * 60 * 60


def test_login_wrong_password_fails(client):
    client.post(
        "/auth/signup",
        json={
            "email": "wrong-password@example.com",
            "password": "password123",
            "nickname": "tester",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "wrong-password@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_logout_invalidates_access_token(client):
    login = _signup_and_login(client)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout = client.post("/auth/logout", headers=headers)
    history = client.get("/me/history", headers=headers)

    assert logout.status_code == 200
    assert logout.json()["status"] == "success"
    assert history.status_code == 401


def test_expired_access_token_is_rejected(client):
    login = _signup_and_login(client, email="expired@example.com")
    token = login.json()["access_token"]

    db = database.SessionLocal()
    try:
        access_token = (
            db.query(database.AccessToken)
            .filter(database.AccessToken.token == main.hash_access_token(token))
            .one()
        )
        access_token.expires_at = database.utc_now() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/me/history",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["status"] == "error"
