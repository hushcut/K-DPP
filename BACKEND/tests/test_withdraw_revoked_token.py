"""탈퇴 요청의 401이 '계정이 이미 없다'는 뜻이 아님을 고정한다.

앱은 탈퇴 요청이 401을 받으면 탈퇴가 끝났다고 안내하면 안 된다. 다른 기기의
비밀번호 변경이나 토큰 만료로도 같은 401이 오고, 그때 계정은 서버에 그대로 남는다.
"""

from datetime import timedelta

import database
import main


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _signup(client, email):
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "tester"},
    )


def _login(client, email, password="password123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _add_history(email):
    session = database.SessionLocal()
    try:
        user_id = (
            session.query(database.User).filter(database.User.email == email).one().id
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
        return user_id
    finally:
        session.close()


def _account_rows(user_id):
    session = database.SessionLocal()
    try:
        users = session.query(database.User).filter(database.User.id == user_id).count()
        history = (
            session.query(database.AnalysisResult)
            .filter(database.AnalysisResult.user_id == user_id)
            .count()
        )
        return users, history
    finally:
        session.close()


def test_withdraw_with_token_revoked_by_password_change_keeps_account(client):
    email = "two-devices@example.com"
    _signup(client, email)
    user_id = _add_history(email)
    phone_token = _login(client, email).json()["access_token"]
    tablet_token = _login(client, email).json()["access_token"]

    # 휴대폰에서 비밀번호를 바꾸면 태블릿 토큰도 함께 폐기된다.
    changed = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth_header(phone_token),
    )
    assert changed.status_code == 200

    # 앱을 켜 둔 태블릿에서 탈퇴하면 비밀번호 확인 전에 401이 난다.
    for password in ("password123", "newpassword456"):
        response = client.post(
            "/auth/withdraw",
            json={"password": password},
            headers=_auth_header(tablet_token),
        )
        assert response.status_code == 401

    # 계정·분석 이력은 그대로이고 새 비밀번호로 로그인된다.
    assert _account_rows(user_id) == (1, 1)
    assert _login(client, email, "newpassword456").status_code == 200


def test_withdraw_with_expired_token_keeps_account(client):
    email = "expired-withdraw@example.com"
    _signup(client, email)
    user_id = _add_history(email)
    token = _login(client, email).json()["access_token"]

    session = database.SessionLocal()
    try:
        row = (
            session.query(database.AccessToken)
            .filter(database.AccessToken.token == main.hash_access_token(token))
            .one()
        )
        row.expires_at = database.utc_now() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(token),
    )

    assert response.status_code == 401
    assert _account_rows(user_id) == (1, 1)
    assert _login(client, email).status_code == 200


def test_withdraw_401_body_does_not_tell_deleted_account_from_revoked_token(client):
    # 탈퇴는 그 사용자의 토큰을 모두 지우므로, 응답이 유실돼 다시 보낸 탈퇴도
    # 다른 기기에서 폐기된 토큰과 똑같이 '토큰 없음' 401을 받는다.
    _signup(client, "deleted@example.com")
    deleted_token = _login(client, "deleted@example.com").json()["access_token"]
    first = client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(deleted_token),
    )
    assert first.status_code == 200
    retried = client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(deleted_token),
    )

    _signup(client, "revoked@example.com")
    revoked_token = _login(client, "revoked@example.com").json()["access_token"]
    other_token = _login(client, "revoked@example.com").json()["access_token"]
    client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=_auth_header(other_token),
    )
    revoked = client.post(
        "/auth/withdraw",
        json={"password": "password123"},
        headers=_auth_header(revoked_token),
    )

    assert retried.status_code == revoked.status_code == 401
    assert retried.json() == revoked.json()
