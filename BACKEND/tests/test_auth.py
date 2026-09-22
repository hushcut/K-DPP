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


# --- 비밀번호 변경 / 회원 탈퇴 -------------------------------------------------


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _make_session(client, email="account@example.com"):
    """가입 후 로그인해 (토큰, 이메일)을 돌려준다."""
    response = _signup_and_login(client, email=email)
    return response.json()["access_token"], email


def test_change_password_success_and_relogin(client):
    token, email = _make_session(client, "changepw@example.com")

    response = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "success"
    # 현재 기기가 계속 쓸 수 있도록 새 토큰을 돌려준다.
    assert body["access_token"]
    assert body["access_token"] != token

    # 새 비밀번호로만 로그인된다.
    assert (
        client.post("/auth/login", json={"email": email, "password": "password123"}).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": email, "password": "newpassword456"}
        ).status_code
        == 200
    )


def test_change_password_invalidates_other_sessions(client):
    token, email = _make_session(client, "sessions@example.com")
    other_token = client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    ).json()["access_token"]

    changed = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )
    new_token = changed.json()["access_token"]

    # 변경에 쓴 토큰과 다른 기기 토큰 모두 끊기고, 새 토큰만 살아 있다.
    assert client.get("/me/history", headers=_auth_header(other_token)).status_code == 401
    assert client.get("/me/history", headers=_auth_header(token)).status_code == 401
    assert client.get("/me/history", headers=_auth_header(new_token)).status_code == 200


def test_change_password_wrong_current_password_fails(client):
    token, _ = _make_session(client, "wrongpw@example.com")

    response = client.post(
        "/auth/password",
        json={"current_password": "notmypassword", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )

    # 401은 세션 만료 전용이다. 재인증 실패를 401로 내면 프론트가 강제 로그아웃한다.
    assert response.status_code == 400
    # 실패했으면 세션은 그대로 살아 있어야 한다.
    assert client.get("/me/history", headers=_auth_header(token)).status_code == 200


def test_change_password_rejects_short_or_same_password(client):
    token, _ = _make_session(client, "rules@example.com")

    too_short = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "short"},
        headers=_auth_header(token),
    )
    same = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "password123"},
        headers=_auth_header(token),
    )
    padded = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": " padded123 "},
        headers=_auth_header(token),
    )

    assert too_short.status_code == 400
    assert same.status_code == 400
    assert padded.status_code == 400


def test_change_password_requires_authentication(client):
    response = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
    )

    assert response.status_code == 401


def test_withdraw_deletes_user_tokens_and_history(client):
    token, email = _make_session(client, "withdraw@example.com")
    session = database.SessionLocal()
    try:
        user_id = (
            session.query(database.User).filter(database.User.email == email).first().id
        )
        session.add(
            database.AnalysisResult(
                user_id=user_id,
                materials='{"cotton": 100.0}',
                carbon_footprint=1.46,
                unit="kg CO2eq",
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    session = database.SessionLocal()
    try:
        assert session.query(database.User).filter(database.User.id == user_id).count() == 0
        assert (
            session.query(database.AccessToken)
            .filter(database.AccessToken.user_id == user_id)
            .count()
            == 0
        )
        assert (
            session.query(database.AnalysisResult)
            .filter(database.AnalysisResult.user_id == user_id)
            .count()
            == 0
        )
    finally:
        session.close()

    # 탈퇴한 계정으로는 다시 로그인할 수 없고, 같은 이메일로 재가입은 가능하다.
    assert (
        client.post("/auth/login", json={"email": email, "password": "password123"}).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "nickname": "again"},
        ).status_code
        == 200
    )


def test_withdraw_wrong_password_keeps_account(client):
    token, email = _make_session(client, "keepme@example.com")

    response = client.post(
        "/auth/withdraw",
        json={"password": "notmypassword"},
        headers=_auth_header(token),
    )

    assert response.status_code == 400
    assert client.get("/me/history", headers=_auth_header(token)).status_code == 200
    assert (
        client.post("/auth/login", json={"email": email, "password": "password123"}).status_code
        == 200
    )


def test_withdraw_requires_authentication(client):
    response = client.post("/auth/withdraw", json={"password": "password123"})

    assert response.status_code == 401


def test_withdraw_does_not_touch_other_users(client):
    keeper_token, keeper_email = _make_session(client, "keeper@example.com")
    leaver_token, _ = _make_session(client, "leaver@example.com")

    client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(leaver_token),
    )

    assert client.get("/me/history", headers=_auth_header(keeper_token)).status_code == 200
    assert (
        client.post(
            "/auth/login", json={"email": keeper_email, "password": "password123"}
        ).status_code
        == 200
    )


def test_change_password_failures_hit_the_login_lockout(client):
    """토큰만 가진 공격자가 이 경로로 비밀번호를 무제한 추측하지 못해야 한다."""
    token, email = _make_session(client, "pwlock@example.com")

    for _ in range(main.LOGIN_MAX_ATTEMPTS):
        assert (
            client.post(
                "/auth/password",
                json={"current_password": "wrong", "new_password": "newpassword456"},
                headers=_auth_header(token),
            ).status_code
            == 400
        )

    locked = client.post(
        "/auth/password",
        json={"current_password": "wrong", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )

    assert locked.status_code == 429
    # 같은 카운터를 쓰므로 로그인도 함께 잠긴다.
    assert (
        client.post("/auth/login", json={"email": email, "password": "password123"}).status_code
        == 429
    )


def test_withdraw_failures_hit_the_login_lockout(client):
    token, _ = _make_session(client, "wdlock@example.com")

    for _ in range(main.LOGIN_MAX_ATTEMPTS):
        assert (
            client.post(
                "/auth/withdraw",
                json={"password": "wrong"},
                headers=_auth_header(token),
            ).status_code
            == 400
        )

    locked = client.post(
        "/auth/withdraw",
        json={"password": "wrong"},
        headers=_auth_header(token),
    )

    assert locked.status_code == 429


def test_successful_reauth_clears_the_lockout_counter(client):
    """정상 사용자가 한두 번 틀린 뒤 성공하면 카운터가 남지 않아야 한다."""
    token, email = _make_session(client, "pwreset@example.com")

    client.post(
        "/auth/password",
        json={"current_password": "wrong", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )
    changed = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth_header(token),
    )

    assert changed.status_code == 200
    assert main._login_failures.get(email) is None
