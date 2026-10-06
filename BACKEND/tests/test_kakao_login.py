"""카카오 로그인(DECISIONS 140·143·152·153) — POST /auth/kakao·카카오 계정 탈퇴·PASSWORD_NOT_SET·리비전.

계약은 BACKEND/API_CONTRACT.md 의 'POST /auth/kakao'·'사용자 객체'와 docs/SCAN_API_CONTRACT.md 2-2·2-3.
카카오 호출 세 함수(main.kakao_token_info·kakao_profile_nickname·kakao_unlink)는 kakao 픽스처가 가짜로
바꿔 끼우고, 진짜 함수의 응답 분류·전체 5초 마감은 맨 아래에서 로컬 가짜 카카오 서버로 시험합니다.
"""

import json
import os
import ssl
import subprocess
import sys
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError

import database
import main
from auth_helpers import signup

APP_ID = 424242
SOCIAL_REVISION = "19b7eee3b75c"
SEED_REVISION = "09f14728ed0b"


class FakeKakao:
    """토큰 → (회원번호, 앱 ID, 카카오 닉네임). 모르는 토큰은 카카오가 거부한 것으로 봅니다."""

    def __init__(self):
        self.accounts = {}
        self.unavailable = set()
        self.fail = {}  # 호출 이름 → 그 호출에서 던질 예외(토큰과 무관)
        self.calls = []
        self.on_profile = None
        self.on_unlink = None

    def add(self, token, subject, nickname="카카오친구", app_id=APP_ID):
        self.accounts[token] = {"subject": str(subject), "app_id": app_id, "nickname": nickname}
        return token

    def _lookup(self, name, token):
        self.calls.append((name, token))
        if name in self.fail:
            raise self.fail[name]
        if token in self.unavailable:
            raise main.KakaoUnavailable(f"fake {name}")
        account = self.accounts.get(token)
        if account is None:
            raise main.KakaoTokenRejected(f"fake {name}")
        return account

    def token_info(self, token):
        account = self._lookup("token_info", token)
        return main.KakaoTokenInfo(subject=account["subject"], app_id=account["app_id"])

    def profile_nickname(self, token, subject):
        account = self._lookup("profile", token)
        assert subject == account["subject"]
        if self.on_profile is not None:
            self.on_profile(token)
        return account["nickname"]

    def unlink(self, token):
        self._lookup("unlink", token)
        if self.on_unlink is not None:
            self.on_unlink(token)

    def count(self, name):
        return sum(1 for called, _ in self.calls if called == name)


@pytest.fixture()
def kakao(client, monkeypatch):
    fake = FakeKakao()
    monkeypatch.setattr(main, "KAKAO_APP_ID", APP_ID)
    monkeypatch.setattr(main, "kakao_token_info", fake.token_info)
    monkeypatch.setattr(main, "kakao_profile_nickname", fake.profile_nickname)
    monkeypatch.setattr(main, "kakao_unlink", fake.unlink)

    # 이메일이 None 인 사용자로 이메일 로그인 잠금 함수를 부르면 모든 카카오 계정이 None 한 칸을
    # 나눠 써, 한 명의 실패 5번으로 전부 60초 잠깁니다(구현 메모 ①). 모든 카카오 테스트에서 지킵니다.
    for name in ("check_login_lockout", "record_login_failure", "clear_login_failures"):
        original = getattr(main, name)

        def guarded(email, _original=original, _name=name):
            assert email is not None, f"{_name}(None)"
            return _original(email)

        monkeypatch.setattr(main, name, guarded)
    return fake


def kakao_login(client, token, nickname=None):
    body = {"access_token": token}
    if nickname is not None:
        body["nickname"] = nickname
    return client.post("/auth/kakao", json=body)


def withdraw(client, session_token, body):
    return client.post("/auth/withdraw", json=body, headers=auth(session_token))


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def rows(sql, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).all()


def count(table):
    return rows(f"SELECT count(*) FROM {table}")[0][0]


def ip_failures():
    with main._login_failures_lock:
        return dict(main._login_ip_failures)


# --- POST /auth/kakao: 새 계정·기존 계정 ---------------------------------------------


def test_first_kakao_login_creates_an_account(client, kakao):
    kakao.add("tok-a", 3000000001, nickname="  카카오 친구  ")

    response = kakao_login(client, "tok-a")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "카카오 계정으로 가입했습니다."
    assert body["is_new_user"] is True
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 24 * 60 * 60
    user = body["user"]
    assert user == {
        "id": user["id"],
        "email": None,
        "nickname": "카카오 친구",
        "login_methods": ["kakao"],
    }
    # 우리 서버 토큰이 바로 쓰이고, /history·/me/history 의 user 도 같은 모양입니다.
    for path in ("/me/history", "/history"):
        history = client.get(path, headers=auth(body["access_token"]))
        assert history.status_code == 200
        assert history.json()["user"] == user
    assert rows(
        "SELECT u.email, u.password_hash, s.provider, s.subject "
        "FROM users u JOIN social_accounts s ON s.user_id = u.id"
    ) == [(None, None, "kakao", "3000000001")]
    assert kakao.count("profile") == 1


def test_next_login_signs_in_the_same_account_and_ignores_the_nickname(client, kakao):
    kakao.add("phone", 77, nickname="처음 닉네임")
    first = kakao_login(client, "phone").json()
    # 다른 기기의 새 토큰, 그사이 카카오 닉네임도 바뀜.
    kakao.add("tablet", 77, nickname="바뀐 닉네임")

    second = kakao_login(client, "tablet", nickname="무시될 이름")

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["is_new_user"] is False
    assert body["message"] == "로그인되었습니다."
    assert body["user"] == first["user"]
    assert body["access_token"] != first["access_token"]
    # 카카오 닉네임은 첫 로그인 때 한 번만 가져옵니다.
    assert kakao.count("profile") == 1
    assert count("users") == 1
    for token in (first["access_token"], body["access_token"]):
        assert client.get("/me/history", headers=auth(token)).status_code == 200


def test_request_nickname_is_used_without_asking_kakao(client, kakao):
    kakao.add("tok", 5, nickname="카카오 이름")

    response = kakao_login(client, "tok", nickname="  내가 정한 이름 ")

    assert response.status_code == 200, response.text
    assert response.json()["user"]["nickname"] == "내가 정한 이름"
    assert kakao.count("profile") == 0


def test_null_nickname_is_the_same_as_not_sending_it(client, kakao):
    kakao.add("tok", 6, nickname="카카오 이름")

    response = client.post("/auth/kakao", json={"access_token": "tok", "nickname": None})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["nickname"] == "카카오 이름"


@pytest.mark.parametrize(
    "kakao_nickname", [None, "", "   ", "가", " 가 ", "줄\n바꿈", "가" * (main.MAX_NICKNAME_LENGTH + 1)]
)
def test_nickname_is_required_when_kakao_has_no_usable_one(client, kakao, kakao_nickname):
    kakao.add("tok", 9, nickname=kakao_nickname)

    response = kakao_login(client, "tok")

    assert response.status_code == 400
    assert response.json()["error_code"] == "SOCIAL_NICKNAME_REQUIRED"
    assert count("users") == 0
    assert ip_failures() == {}
    # 앱은 닉네임을 받아 같은 토큰으로 다시 보냅니다.
    retry = kakao_login(client, "tok", nickname="새 닉네임")
    assert retry.status_code == 200, retry.text
    assert retry.json()["is_new_user"] is True
    assert retry.json()["user"]["nickname"] == "새 닉네임"


@pytest.mark.parametrize(
    "nickname, message",
    [
        ("가", "닉네임은 2자 이상 입력해 주세요."),
        ("   ", "닉네임은 2자 이상 입력해 주세요."),
        ("벨\u0007소리", "닉네임에 쓸 수 없는 문자가 있습니다."),
    ],
)
def test_bad_request_nickname_is_400_without_asking_kakao(client, kakao, nickname, message):
    kakao.add("tok", 1)

    response = kakao_login(client, "tok", nickname=nickname)

    assert response.status_code == 400
    assert response.json()["error_code"] == "BAD_REQUEST"
    assert response.json()["message"] == message
    assert kakao.calls == []
    assert ip_failures() == {}


def test_kakao_nickname_at_the_length_limit_is_used(client, kakao):
    nickname = "가" * main.MAX_NICKNAME_LENGTH
    kakao.add("tok", 2, nickname=f" {nickname} ")

    response = kakao_login(client, "tok")

    assert response.status_code == 200, response.text
    assert response.json()["user"]["nickname"] == nickname


def test_overlong_request_nickname_is_422_without_asking_kakao(client, kakao):
    kakao.add("tok", 3)

    for nickname in ("가" * (main.MAX_NICKNAME_LENGTH + 1), "x" * 1_000_000):
        response = kakao_login(client, "tok", nickname=nickname)

        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"
        assert response.json()["detail"][0]["loc"] == ["body", "nickname"]
        # 거부 응답은 입력을 되돌려주지 않습니다(증폭 방지).
        assert len(response.content) < 2000

    assert kakao.calls == []
    assert ip_failures() == {}
    assert count("users") == 0


def test_lone_surrogate_nickname_is_422_not_500(client, kakao):
    kakao.add("tok", 1)

    response = client.post(
        "/auth/kakao",
        content='{"access_token": "tok", "nickname": "ab\\ud800cd"}',
        headers={"Content-Type": "application/json"},
    )

    # 길이 상한(StringConstraints)이 붙은 칸이라 Pydantic 이 핸들러 전에 string_unicode 로 거부합니다.
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert kakao.calls == []


# --- 형식·본문·설정 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    ["", "   ", "two words", "tab\tinside", "한글토큰", "x" * 1025, "nul\u0000byte", "　"],
)
def test_malformed_tokens_are_400_and_never_reach_kakao(client, kakao, token):
    response = kakao_login(client, token)

    assert response.status_code == 400
    assert response.json()["error_code"] == "BAD_REQUEST"
    assert kakao.calls == []
    assert ip_failures() == {}


def test_tokens_are_trimmed_and_1024_characters_are_accepted(client, kakao):
    longest = "x" * 1024
    kakao.add(longest, 1)
    kakao.add("tok", 2)

    assert kakao_login(client, longest).status_code == 200
    assert kakao_login(client, "  tok\n").status_code == 200
    assert [token for name, token in kakao.calls if name == "token_info"] == [longest, "tok"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"access_token": None},
        {"access_token": 123},
        {"access_token": ["tok"]},
        {"access_token": "tok", "nickname": 5},
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_body_shape_errors_are_422_before_anything_else(client, monkeypatch, body, enabled):
    # 앱 ID 가 없어도(503 보다) 먼저 422 — 앱 버그를 먼저 드러냅니다.
    monkeypatch.setattr(main, "KAKAO_APP_ID", APP_ID if enabled else None)

    response = client.post("/auth/kakao", json=body)

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_kakao_login_is_503_without_an_app_id(client, monkeypatch):
    assert main.KAKAO_APP_ID is None  # 로컬·CI 기본
    asked = []
    monkeypatch.setattr(main, "kakao_token_info", lambda token: asked.append(token))

    for token in ("tok", "two words"):  # 형식 검사(400)보다 먼저
        response = kakao_login(client, token)
        assert response.status_code == 503
        assert response.json()["error_code"] == "SOCIAL_LOGIN_UNAVAILABLE"
    assert asked == []
    assert ip_failures() == {}


def test_authorization_header_is_ignored(client, kakao):
    kakao.add("tok", 1)

    response = client.post(
        "/auth/kakao", json={"access_token": "tok"}, headers={"Authorization": "Bearer nonsense"}
    )

    assert response.status_code == 200


# --- 거부·장애·횟수 제한 ---------------------------------------------------------------


def test_rejected_tokens_are_401_and_share_the_login_ip_record(client, kakao, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 3)
    kakao.add("good", 1)
    kakao.add("other-app", 2, app_id=APP_ID + 1)

    for token in ("expired", "other-app"):
        response = kakao_login(client, token)
        assert response.status_code == 401
        assert response.json()["error_code"] == "SOCIAL_TOKEN_INVALID"
    assert ip_failures()["testclient"][0] == 2
    # 이메일 로그인 실패와 같은 기록입니다.
    wrong = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass"})
    assert wrong.status_code == 401

    blocked = kakao_login(client, "good")

    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert blocked.json()["message"].startswith("로그인 시도가 너무 많습니다. 15분 후")
    # 막힌 요청은 카카오에 묻지 않습니다.
    assert kakao.count("token_info") == 2
    assert count("users") == 0


def test_success_nickname_required_and_outages_do_not_count(client, kakao, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 1)
    kakao.add("ok", 1)
    kakao.add("no-nickname", 2, nickname=None)
    kakao.add("down", 3)
    kakao.unavailable.add("down")

    for _ in range(3):
        assert kakao_login(client, "ok").status_code == 200
    assert kakao_login(client, "no-nickname").status_code == 400
    outage = kakao_login(client, "down")
    assert outage.status_code == 502
    assert outage.json()["error_code"] == "SOCIAL_PROVIDER_UNAVAILABLE"

    assert ip_failures() == {}
    assert kakao_login(client, "ok").status_code == 200


def test_profile_call_failures_follow_the_same_table(client, kakao):
    kakao.add("tok", 1)

    kakao.fail["profile"] = main.KakaoUnavailable("fake")
    assert kakao_login(client, "tok").status_code == 502
    assert ip_failures() == {}

    # 토큰 확인과 닉네임 조회 사이에 토큰이 만료된 경우.
    kakao.fail["profile"] = main.KakaoTokenRejected("fake")
    expired = kakao_login(client, "tok")
    assert expired.status_code == 401
    assert expired.json()["error_code"] == "SOCIAL_TOKEN_INVALID"
    assert ip_failures()["testclient"][0] == 1
    assert count("users") == 0


def test_server_errors_release_the_ip_reservation(client, kakao, monkeypatch):
    server = TestClient(main.app, raise_server_exceptions=False)
    kakao.add("tok", 1)
    kakao.fail["profile"] = RuntimeError("boom")

    assert kakao_login(server, "tok").status_code == 500
    assert ip_failures() == {}


def test_new_kakao_accounts_do_not_count_toward_the_signup_ip_limit(client, kakao, monkeypatch):
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 1)

    for i in range(3):
        kakao.add(f"tok-{i}", 100 + i)
        assert kakao_login(client, f"tok-{i}").json()["is_new_user"] is True

    assert main._signup_ip_attempts == {}
    assert signup(client, "after-kakao@example.com").status_code == 200


def test_outage_logs_never_contain_the_token(client, kakao, capsys):
    secret = "kakao-secret-token-123"
    kakao.add(secret, 1)
    kakao.fail["token_info"] = main.KakaoUnavailable("/v1/user/access_token_info: ReadTimeout")

    assert kakao_login(client, secret).status_code == 502

    err = capsys.readouterr().err
    assert "[kakao] 로그인 실패" in err
    assert secret not in err


# --- 비밀번호 계정과의 경계 -----------------------------------------------------------


def test_email_account_responses_list_password_login(client):
    created = signup(client, "methods@example.com")
    assert created.json()["user"]["login_methods"] == ["password"]
    login = client.post("/auth/login", json={"email": "methods@example.com", "password": "password123"})
    assert login.json()["user"]["login_methods"] == ["password"]
    token = login.json()["access_token"]
    for path in ("/me/history", "/history"):
        assert client.get(path, headers=auth(token)).json()["user"]["login_methods"] == ["password"]
    changed = client.post(
        "/auth/password",
        json={"current_password": "password123", "new_password": "newpassword456"},
        headers=auth(token),
    )
    assert changed.json()["user"]["login_methods"] == ["password"]


def test_password_change_is_password_not_set_for_kakao_accounts(client, kakao):
    kakao.add("tok", 1)
    token = kakao_login(client, "tok").json()["access_token"]

    for _ in range(main.LOGIN_MAX_ATTEMPTS + 2):
        response = client.post(
            "/auth/password",
            json={"current_password": "whatever1", "new_password": "newpassword456"},
            headers=auth(token),
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "PASSWORD_NOT_SET"
        assert response.json()["message"] == "비밀번호로 가입한 계정이 아닙니다."

    # 로그인 잠금 카운터에 남지 않고, 세션도 그대로입니다.
    assert main._login_failures == {}
    assert client.get("/me/history", headers=auth(token)).status_code == 200


def test_kakao_and_email_lockouts_do_not_touch_each_other(client, kakao):
    email = "locked@example.com"
    signup(client, email)
    for _ in range(main.LOGIN_MAX_ATTEMPTS):
        client.post("/auth/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 429

    kakao.add("tok", 1)
    assert kakao_login(client, "tok").status_code == 200
    kakao.add("tok-2", 2)
    assert kakao_login(client, "tok-2").status_code == 200
    assert set(main._login_failures) == {email}


def test_email_login_and_reset_never_match_kakao_accounts(client, kakao, monkeypatch):
    # 이메일이 NULL 인 행이 이메일 조회에 걸리지 않습니다(User.email == None 은 IS NULL 이라 금지).
    kakao.add("tok", 1)
    kakao_login(client, "tok")
    for email in ("", " "):
        assert client.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    assert signup(client, "real@example.com").status_code == 200
    assert count("users") == 2


# --- 카카오 계정 탈퇴 -----------------------------------------------------------------


def _kakao_session(client, kakao, token="tok", subject=4242):
    kakao.add(token, subject)
    body = kakao_login(client, token).json()
    return body["access_token"], body["user"]["id"]


def test_withdraw_kakao_account_deletes_everything_then_unlinks(client, kakao):
    session, user_id = _kakao_session(client, kakao)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_results (user_id, materials, carbon_footprint, unit, "
                "unknown_materials, created_at) VALUES (:u, '{}', 1.0, 'kg CO2eq', '[]', now())"
            ),
            {"u": user_id},
        )
    seen = {}

    def on_unlink(token):
        seen["token"] = token
        seen["users_left"] = rows("SELECT count(*) FROM users WHERE id = :id", id=user_id)[0][0]

    kakao.on_unlink = on_unlink
    kakao.add("reauth", 4242)  # 탈퇴 확인 단계의 재인증 로그인으로 받은 토큰

    response = withdraw(client, session, {"kakao_access_token": "reauth"})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "success", "message": "회원 탈퇴가 완료되었습니다."}
    # 삭제를 커밋한 뒤에 그 토큰으로 연결을 끊습니다.
    assert seen == {"token": "reauth", "users_left": 0}
    for table in ("users", "access_tokens", "analysis_results", "social_accounts"):
        assert count(table) == 0, table
    assert ip_failures() == {}
    # 같은 카카오 계정으로 다시 로그인하면 새 계정입니다.
    again = kakao_login(client, "tok").json()
    assert again["is_new_user"] is True
    assert again["user"]["id"] != user_id


def test_withdraw_reads_only_the_field_that_matches_the_account(client, kakao):
    session, _ = _kakao_session(client, kakao)
    for body in ({}, {"password": "password123"}, {"kakao_access_token": None}):
        response = withdraw(client, session, body)
        assert response.status_code == 400
        assert response.json()["error_code"] == "BAD_REQUEST"
        assert response.json()["message"] == "카카오 로그인으로 탈퇴를 확인해 주세요."

    signup(client, "pw@example.com")
    pw_session = client.post(
        "/auth/login", json={"email": "pw@example.com", "password": "password123"}
    ).json()["access_token"]
    for body in ({}, {"kakao_access_token": "tok"}):
        response = withdraw(client, pw_session, body)
        assert response.status_code == 400
        assert response.json()["message"] == "비밀번호를 입력해 주세요."
    assert kakao.count("token_info") == 1  # 위 _kakao_session 의 로그인 한 번뿐

    # 맞지 않는 칸은 무시합니다.
    assert withdraw(client, pw_session, {"password": "password123", "kakao_access_token": "x"}).status_code == 200
    assert kakao.count("token_info") == 1
    assert count("users") == 1


def test_withdraw_checks_the_session_then_the_body_shape(client, kakao):
    session, _ = _kakao_session(client, kakao)

    no_session = client.post("/auth/withdraw", json={"kakao_access_token": 5})
    assert no_session.status_code == 401
    bad_shape = withdraw(client, session, {"kakao_access_token": 5})
    assert bad_shape.status_code == 422


def test_withdraw_rejections_keep_the_account(client, kakao, monkeypatch):
    session, _ = _kakao_session(client, kakao, token="tok", subject=1)
    kakao.add("someone-else", 2)
    kakao.add("other-app", 1, app_id=APP_ID + 1)
    kakao.add("down", 1)
    kakao.unavailable.add("down")

    def expect(token, status, error_code):
        response = withdraw(client, session, {"kakao_access_token": token})
        assert response.status_code == status, (token, response.text)
        assert response.json()["error_code"] == error_code

    expect("expired", 400, "SOCIAL_TOKEN_INVALID")  # 로그인한 요청이라 401 이 아니라 400
    expect("other-app", 400, "SOCIAL_TOKEN_INVALID")
    assert ip_failures()["testclient"][0] == 2
    expect("someone-else", 400, "SOCIAL_ACCOUNT_MISMATCH")
    expect("down", 502, "SOCIAL_PROVIDER_UNAVAILABLE")
    asked = kakao.count("token_info")
    expect("two words", 400, "BAD_REQUEST")
    assert kakao.count("token_info") == asked
    # 대조 실패·장애·형식 오류는 IP 기록에 남지 않습니다.
    assert ip_failures()["testclient"][0] == 2

    monkeypatch.setattr(main, "KAKAO_APP_ID", None)
    expect("tok", 503, "SOCIAL_LOGIN_UNAVAILABLE")
    monkeypatch.setattr(main, "KAKAO_APP_ID", APP_ID)
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 2)
    expect("tok", 429, "TOO_MANY_ATTEMPTS")

    assert kakao.count("unlink") == 0
    assert count("users") == 1
    assert client.get("/me/history", headers=auth(session)).status_code == 200


@pytest.mark.parametrize(
    "error",
    [main.KakaoUnavailable("/v1/user/unlink: ReadTimeout"), RuntimeError("boom kakao-secret-xyz")],
)
def test_unlink_failure_still_withdraws_and_never_logs_the_token(client, kakao, capsys, error):
    session, user_id = _kakao_session(client, kakao, token="kakao-secret-xyz")
    kakao.fail["unlink"] = error

    response = withdraw(client, session, {"kakao_access_token": "kakao-secret-xyz"})

    assert response.status_code == 200
    assert count("users") == 0
    err = capsys.readouterr().err
    assert f"탈퇴한 사용자 {user_id} 의 카카오 연결 끊기 실패" in err
    assert "kakao-secret-xyz" not in err


# --- 경합 -----------------------------------------------------------------------------


def _run_together(*requests):
    results = [None] * len(requests)

    def run(i):
        results[i] = requests[i]()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(requests))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_concurrent_first_logins_create_one_account(client, kakao):
    kakao.add("device-a", 555, nickname="동시 가입")
    kakao.add("device-b", 555, nickname="동시 가입")
    # 둘 다 '계정 없음'을 본 뒤에 만들도록, 닉네임 조회(조회 뒤·INSERT 전)에서 서로를 기다립니다.
    barrier = threading.Barrier(2, timeout=10)
    kakao.on_profile = lambda token: barrier.wait()

    a, b = _run_together(
        lambda: kakao_login(client, "device-a"), lambda: kakao_login(client, "device-b")
    )

    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert sorted([a.json()["is_new_user"], b.json()["is_new_user"]]) == [False, True]
    assert a.json()["user"] == b.json()["user"]
    assert (count("users"), count("social_accounts"), count("access_tokens")) == (1, 1, 2)


def _pause_on(statement_prefix):
    reached, release, armed = threading.Event(), threading.Event(), [True]

    def listener(conn, cursor, statement, parameters, context, executemany):
        if armed[0] and statement.startswith(statement_prefix):
            armed[0] = False
            reached.set()
            release.wait(10)

    event.listen(database.engine, "after_cursor_execute", listener)
    return reached, release, listener


def test_login_waiting_on_a_withdrawal_gets_a_new_account_not_an_orphan_token(client, kakao):
    server = TestClient(main.app, raise_server_exceptions=False)
    session, old_id = _kakao_session(server, kakao, token="phone", subject=888)
    kakao.add("tablet", 888)
    # 탈퇴가 users 를 지우고 커밋하기 전에 멈춥니다(users 행 잠금을 쥔 채).
    reached, release, listener = _pause_on("DELETE FROM users")
    out = {}
    try:
        leaving = threading.Thread(
            target=lambda: out.setdefault(
                "withdraw", withdraw(server, session, {"kakao_access_token": "phone"})
            )
        )
        leaving.start()
        assert reached.wait(10)
        arriving = threading.Thread(
            target=lambda: out.setdefault("login", kakao_login(server, "tablet"))
        )
        arriving.start()
        time.sleep(0.3)  # 로그인이 users 행 잠금에서 기다리게
        release.set()
        leaving.join(30)
        arriving.join(30)
    finally:
        event.remove(database.engine, "after_cursor_execute", listener)

    assert out["withdraw"].status_code == 200, out["withdraw"].text
    assert out["login"].status_code == 200, out["login"].text
    # 탈퇴가 먼저 끝났으므로 로그인은 지워진 계정 대신 새 계정을 만듭니다(받아들인 한계 — 계약).
    assert out["login"].json()["is_new_user"] is True
    assert out["login"].json()["user"]["id"] != old_id
    assert rows("SELECT count(*) FROM access_tokens WHERE user_id = :id", id=old_id)[0][0] == 0
    assert count("users") == 1


def test_withdrawal_waiting_on_a_login_removes_the_new_token_too(client, kakao):
    server = TestClient(main.app, raise_server_exceptions=False)
    session, user_id = _kakao_session(server, kakao, token="phone", subject=999)
    kakao.add("tablet", 999)
    # 로그인이 users 행을 잠그고 토큰을 넣은 뒤, 커밋하기 전에 멈춥니다.
    reached, release, listener = _pause_on("INSERT INTO access_tokens")
    out = {}
    try:
        arriving = threading.Thread(
            target=lambda: out.setdefault("login", kakao_login(server, "tablet"))
        )
        arriving.start()
        assert reached.wait(10)
        leaving = threading.Thread(
            target=lambda: out.setdefault(
                "withdraw", withdraw(server, session, {"kakao_access_token": "phone"})
            )
        )
        leaving.start()
        time.sleep(0.3)  # 탈퇴가 users 행 잠금에서 기다리게
        release.set()
        arriving.join(30)
        leaving.join(30)
    finally:
        event.remove(database.engine, "after_cursor_execute", listener)

    assert out["login"].status_code == 200, out["login"].text
    assert out["login"].json()["is_new_user"] is False
    assert out["withdraw"].status_code == 200, out["withdraw"].text
    # 로그인이 먼저 커밋한 토큰도 탈퇴가 함께 지웁니다(외래 키 오류 500 없음).
    new_token = out["login"].json()["access_token"]
    assert server.get("/me/history", headers=auth(new_token)).status_code == 401
    for table in ("users", "access_tokens", "social_accounts"):
        assert count(table) == 0, table


# --- 카카오를 기다리는 동안·커밋 경계 (변이 검사가 찾은 빈틈) -------------------------------


def _idle_in_transaction():
    # 트랜잭션을 연 채 쉬고 있는 연결 수(이 확인 연결은 뺌).
    return rows(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"
    )[0][0]


def test_no_transaction_is_held_while_asking_kakao_for_the_nickname(client, kakao):
    kakao.add("tok", 1)
    seen = []
    kakao.on_profile = lambda token: seen.append(_idle_in_transaction())

    assert kakao_login(client, "tok").status_code == 200
    assert seen == [0]


def test_no_transaction_is_held_while_confirming_a_withdrawal(client, kakao, monkeypatch):
    session, _ = _kakao_session(client, kakao)
    seen = []
    original = main.kakao_token_info

    def spy(token):
        seen.append(_idle_in_transaction())
        return original(token)

    monkeypatch.setattr(main, "kakao_token_info", spy)

    assert withdraw(client, session, {"kakao_access_token": "tok"}).status_code == 200
    assert seen == [0]


@pytest.mark.parametrize("existing", [True, False], ids=["existing", "new"])
def test_user_payload_is_built_before_the_commit(client, kakao, existing):
    # 커밋과 응답 사이에 다른 기기의 탈퇴가 끼어도, 행을 쥔 채 만든 응답이라 500 이 아닙니다.
    server = TestClient(main.app, raise_server_exceptions=False)
    kakao.add("tok", 1)
    if existing:
        assert kakao_login(server, "tok").status_code == 200
    armed = [True]

    def wipe(session):
        if armed[0]:
            armed[0] = False
            with database.engine.begin() as connection:
                for table in ("access_tokens", "social_accounts", "users"):
                    connection.execute(text(f"DELETE FROM {table}"))

    event.listen(database.SessionLocal, "after_commit", wipe)
    try:
        response = kakao_login(server, "tok")
    finally:
        event.remove(database.SessionLocal, "after_commit", wipe)

    assert response.status_code == 200, response.text
    assert response.json()["user"]["login_methods"] == ["kakao"]


def test_withdrawal_that_lost_the_race_while_asking_kakao_is_401(client, kakao, monkeypatch):
    session, user_id = _kakao_session(client, kakao)
    original = main.kakao_token_info

    def other_device_withdraws_first(token):
        with database.engine.begin() as connection:
            for table in ("access_tokens", "social_accounts", "analysis_results"):
                connection.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), {"u": user_id})
            connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        return original(token)

    monkeypatch.setattr(main, "kakao_token_info", other_device_withdraws_first)

    response = withdraw(client, session, {"kakao_access_token": "tok"})

    # 대조(SOCIAL_ACCOUNT_MISMATCH)까지 가지 않고 세션 만료, 연결 끊기도 부르지 않습니다.
    assert response.status_code == 401, response.text
    assert kakao.count("unlink") == 0


def test_only_the_social_unique_violation_is_retried(client, kakao):
    kakao.add("tok", 1)
    inserts = []

    def count_user_inserts(conn, cursor, statement, *args):
        if statement.startswith("INSERT INTO users"):
            inserts.append(statement)

    with database.engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE users ADD CONSTRAINT ck_tmp_boom CHECK (nickname <> '터지는 이름')")
        )
    event.listen(database.engine, "before_cursor_execute", count_user_inserts)
    try:
        with pytest.raises(IntegrityError, match="ck_tmp_boom"):
            kakao_login(client, "tok", nickname="터지는 이름")
    finally:
        event.remove(database.engine, "before_cursor_execute", count_user_inserts)
        with database.engine.begin() as connection:
            connection.execute(text("ALTER TABLE users DROP CONSTRAINT ck_tmp_boom"))
    assert len(inserts) == 1


def test_missing_withdraw_field_is_400_before_the_503_setting_check(client, kakao, monkeypatch):
    session, _ = _kakao_session(client, kakao)
    monkeypatch.setattr(main, "KAKAO_APP_ID", None)

    response = withdraw(client, session, {})

    assert response.status_code == 400
    assert response.json()["message"] == "카카오 로그인으로 탈퇴를 확인해 주세요."


# --- DB 제약·리비전 -------------------------------------------------------------------


def _insert_user(connection, email, password_hash):
    connection.execute(
        text(
            "INSERT INTO users (email, nickname, password_hash, created_at) "
            "VALUES (:email, 'n', :password_hash, now())"
        ),
        {"email": email, "password_hash": password_hash},
    )


@pytest.mark.parametrize("email, password_hash", [("only-email@example.com", None), (None, "hash")])
def test_users_need_both_email_and_password_or_neither(client, email, password_hash):
    with pytest.raises(IntegrityError, match="ck_users_email_password_together"):
        with database.engine.begin() as connection:
            _insert_user(connection, email, password_hash)


def test_many_users_without_email_and_social_uniqueness(client):
    with database.engine.begin() as connection:
        _insert_user(connection, None, None)
        _insert_user(connection, None, None)
        ids = [row[0] for row in connection.execute(text("SELECT id FROM users ORDER BY id"))]
        connection.execute(
            text(
                "INSERT INTO social_accounts (user_id, provider, subject, created_at) "
                "VALUES (:u, 'kakao', '1', now())"
            ),
            {"u": ids[0]},
        )
    duplicates = [
        (ids[1], "kakao", "1", "uq_social_accounts_provider_subject"),
        (ids[0], "kakao", "2", "uq_social_accounts_user_id_provider"),
    ]
    for user_id, provider, subject, constraint in duplicates:
        with pytest.raises(IntegrityError, match=constraint):
            with database.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO social_accounts (user_id, provider, subject, created_at) "
                        "VALUES (:u, :p, :s, now())"
                    ),
                    {"u": user_id, "p": provider, "s": subject},
                )


def test_social_revision_keeps_existing_email_users(alembic_config):
    command.upgrade(alembic_config, SEED_REVISION)
    with database.engine.begin() as connection:
        _insert_user(connection, "old@example.com", "hash")

    command.upgrade(alembic_config, "head")

    assert rows("SELECT email, password_hash FROM users") == [("old@example.com", "hash")]
    columns = {c["name"]: c for c in inspect(database.engine).get_columns("users")}
    assert columns["email"]["nullable"] and columns["password_hash"]["nullable"]


def test_social_revision_downgrade_refuses_while_kakao_users_exist(alembic_config):
    command.upgrade(alembic_config, "head")
    with database.engine.begin() as connection:
        _insert_user(connection, "keep@example.com", "hash")
        _insert_user(connection, None, None)

    with pytest.raises(RuntimeError, match="카카오 계정"):
        command.downgrade(alembic_config, SEED_REVISION)
    assert rows("SELECT version_num FROM alembic_version") == [(SOCIAL_REVISION,)]

    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email IS NULL"))
    command.downgrade(alembic_config, SEED_REVISION)

    assert "social_accounts" not in inspect(database.engine).get_table_names()
    columns = {c["name"]: c for c in inspect(database.engine).get_columns("users")}
    assert not columns["email"]["nullable"] and not columns["password_hash"]["nullable"]
    assert rows("SELECT email FROM users") == [("keep@example.com",)]
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


# --- 설정 ---------------------------------------------------------------------------


def test_parse_kakao_app_id():
    for value in (None, "", "   "):
        assert main.parse_kakao_app_id(value) is None
    assert main.parse_kakao_app_id("1234") == 1234
    assert main.parse_kakao_app_id(" 1234 ") == 1234
    for value in ("0", "-1", "12.5", "abc", "١٢", "12 34", "0x10"):
        with pytest.raises(ValueError):
            main.parse_kakao_app_id(value)


def _import_main_with(**env):
    # 설정은 import 때 읽으므로 환경변수를 바꾼 별도 프로세스에서 봅니다.
    return subprocess.run(
        [sys.executable, "-c", "import main; print(main.KAKAO_APP_ID)"],
        cwd=Path(main.__file__).parent,
        env=dict(os.environ, **env),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_kakao_app_id_setting_at_startup():
    bad = _import_main_with(K_DPP_KAKAO_APP_ID="native-app-key")
    assert bad.returncode != 0
    assert "K_DPP_KAKAO_APP_ID" in bad.stderr
    good = _import_main_with(K_DPP_KAKAO_APP_ID="1234")
    assert good.returncode == 0, good.stderr
    assert good.stdout.strip().splitlines()[-1] == "1234"


# --- 진짜 카카오 호출 함수 (로컬 가짜 카카오 서버) ---------------------------------------


class _FakeKakaoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply()

    def do_POST(self):
        self._reply()

    def _reply(self):
        server = self.server
        server.requests.append((self.command, self.path, dict(self.headers)))
        status, body, gap = server.routes[self.path.split("?")[0]]
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json;charset=UTF-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if gap:
                # 한 바이트씩 gap 초마다 — 단계별 시간 제한엔 안 걸리고 전체 마감에만 걸리게.
                for byte in payload:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(gap)
            else:
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


@pytest.fixture()
def kakao_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeKakaoHandler)
    server.daemon_threads = True
    server.routes = {}
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(main, "KAKAO_API_BASE", f"http://127.0.0.1:{server.server_port}")
    yield server
    server.shutdown()
    server.server_close()


TOKEN_INFO = "/v1/user/access_token_info"
USER_ME = "/v2/user/me"
UNLINK = "/v1/user/unlink"


def test_token_info_reads_the_member_id_and_app_id(kakao_server):
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 3000000001, "expires_in": 7199, "app_id": 1234}, 0)

    info = main.kakao_token_info("tok-x")

    assert info == main.KakaoTokenInfo(subject="3000000001", app_id=1234)
    method, path, headers = kakao_server.requests[-1]
    assert (method, path) == ("GET", TOKEN_INFO)
    assert headers["Authorization"] == "Bearer tok-x"


@pytest.mark.parametrize(
    "status, body",
    [
        (401, {"msg": "this access token does not exist", "code": -401}),
        (400, {"msg": "invalid argument", "code": -2}),
    ],
)
def test_token_rejections_are_read_from_the_body_code(kakao_server, status, body):
    kakao_server.routes[TOKEN_INFO] = (status, body, 0)

    with pytest.raises(main.KakaoTokenRejected):
        main.kakao_token_info("tok")


@pytest.mark.parametrize(
    "status, body",
    [
        (400, {"msg": "internal error", "code": -1}),  # 일시 장애가 HTTP 400 으로 옴
        (401, {"msg": "?"}),
        (500, b"<html>bad gateway</html>"),
        (503, {"code": "-401"}),
        (200, b"not json"),
        (200, b"\xff\xfe"),
        # json 이 RecursionError 를 냄(ValueError 아님)
        pytest.param(200, b"[" * 100_000 + b"]" * 100_000, id="deep-json"),
        (200, [1, 2]),
        (200, {"id": "3000", "app_id": 1234}),
        (200, {"id": True, "app_id": 1234}),
        (200, {"id": 0, "app_id": 1234}),
        (200, {"id": -5, "app_id": 1234}),
        (200, {"app_id": 1234}),
        (200, {"id": 5}),
        (200, {"id": 5, "app_id": "1234"}),
    ],
)
def test_other_token_info_answers_are_unavailable(kakao_server, status, body):
    kakao_server.routes[TOKEN_INFO] = (status, body, 0)

    with pytest.raises(main.KakaoUnavailable):
        main.kakao_token_info("tok")


def test_connection_failure_is_unavailable(monkeypatch):
    with ThreadingHTTPServer(("127.0.0.1", 0), _FakeKakaoHandler) as closed:
        port = closed.server_port
    monkeypatch.setattr(main, "KAKAO_API_BASE", f"http://127.0.0.1:{port}")

    with pytest.raises(main.KakaoUnavailable):
        main.kakao_token_info("tok")


@pytest.mark.parametrize(
    "error",
    [ssl.SSLError("record layer failure"), ConnectionResetError(), TimeoutError()],
    ids=["tls-record", "reset", "timeout"],
)
def test_transport_errors_outside_httpx_are_unavailable(monkeypatch, error):
    # 응답을 읽는 중의 TLS 오류는 httpcore 가 httpx 예외로 바꾸지 않고 ssl.SSLError 로 올라옵니다.
    async def failing(*args):
        raise error

    monkeypatch.setattr(main, "_send_kakao_request", failing)

    with pytest.raises(main.KakaoUnavailable, match=type(error).__name__):
        main.kakao_token_info("tok")


def test_proxy_environment_variables_are_ignored(kakao_server, monkeypatch):
    # 잘못된 프록시 값(지원 안 하는 스킴·SOCKS·깨진 주소)이 500 을 내거나 호출을 엉뚱한 곳으로 보내지 않게.
    for name, value in (
        ("HTTP_PROXY", "ftp://proxy.invalid"),
        ("ALL_PROXY", "socks5://proxy.invalid:1080"),
        ("HTTPS_PROXY", "::bad"),
    ):
        monkeypatch.setenv(name, value)
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1234}, 0)

    assert main.kakao_token_info("tok") == main.KakaoTokenInfo(subject="1", app_id=1234)


def _limit_kakao_calls(monkeypatch, slots):
    monkeypatch.setattr(main, "KAKAO_MAX_CONCURRENT_CALLS", slots)
    semaphore = threading.BoundedSemaphore(slots)
    monkeypatch.setattr(main, "_kakao_call_slots", semaphore)
    return semaphore


def test_full_call_slots_fail_fast_without_asking_kakao(client, kakao_server, monkeypatch):
    # DECISIONS 156: 카카오가 느려 자리가 다 찼으면 기다리지 않고 곧바로 502(IP 기록은 되돌림).
    semaphore = _limit_kakao_calls(monkeypatch, 1)
    monkeypatch.setattr(main, "KAKAO_APP_ID", 1234)
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1234}, 0)
    kakao_server.routes[USER_ME] = (200, {"id": 1, "kakao_account": {"profile": {"nickname": "자리"}}}, 0)
    assert semaphore.acquire(blocking=False)
    try:
        with pytest.raises(main.KakaoUnavailable, match="동시 호출 상한"):
            main.kakao_token_info("tok")
        response = kakao_login(client, "tok")
        assert response.status_code == 502
        assert response.json()["error_code"] == "SOCIAL_PROVIDER_UNAVAILABLE"
        assert ip_failures() == {}
    finally:
        semaphore.release()
    assert kakao_server.requests == []
    assert kakao_login(client, "tok").status_code == 200


def test_call_slots_come_back_after_every_outcome(kakao_server, monkeypatch):
    _limit_kakao_calls(monkeypatch, 1)
    monkeypatch.setattr(main, "KAKAO_CALL_TIMEOUT_SECONDS", 0.3)
    outcomes = [
        ((401, {"code": -401}, 0), main.KakaoTokenRejected),
        ((500, b"oops", 0), main.KakaoUnavailable),
        ((200, {"id": 1, "app_id": 1, "pad": "x" * 20}, 0.1), main.KakaoUnavailable),  # 마감
    ]
    for route, error in outcomes:
        kakao_server.routes[TOKEN_INFO] = route
        with pytest.raises(error):
            main.kakao_token_info("tok")

    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1}, 0)
    assert main.kakao_token_info("tok").subject == "1"


def test_concurrent_calls_beyond_the_limit_fail_immediately(kakao_server, monkeypatch):
    _limit_kakao_calls(monkeypatch, 3)
    # 한 호출이 약 0.8초 걸리는 느린 카카오.
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1, "pad": "x" * 10}, 0.02)
    results = []

    def call():
        started = time.monotonic()
        try:
            main.kakao_token_info("tok")
            results.append(("ok", time.monotonic() - started))
        except main.KakaoUnavailable as error:
            results.append((str(error), time.monotonic() - started))

    threads = [threading.Thread(target=call) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    outcomes = [outcome for outcome, _ in results]
    assert outcomes.count("ok") == 3
    assert outcomes.count("/v1/user/access_token_info: 동시 호출 상한(3건)") == 3
    assert all(elapsed < 0.3 for outcome, elapsed in results if outcome != "ok")
    assert len(kakao_server.requests) == 3


def test_each_call_has_one_overall_deadline(kakao_server, monkeypatch):
    # 0.2초마다 한 바이트 — 읽기 단계 제한(0.6초)엔 한 번도 안 걸리지만 다 받으려면 수 초가 걸립니다.
    monkeypatch.setattr(main, "KAKAO_CALL_TIMEOUT_SECONDS", 0.6)
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1234, "pad": "x" * 20}, 0.2)

    started = time.monotonic()
    with pytest.raises(main.KakaoUnavailable, match="TimeoutError"):
        main.kakao_token_info("tok")
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize(
    "account, expected",
    [
        ({"profile": {"nickname": "홍길동", "is_default_nickname": False}}, "홍길동"),
        ({"profile": {"nickname": "홍길동"}}, "홍길동"),
        ({"profile": {"nickname": "닉네임을 등록해주세요", "is_default_nickname": True}}, None),
        ({"profile_nickname_needs_agreement": True}, None),
        ({"profile": {"nickname": 7}}, None),
        ({"profile": "홍길동"}, None),
        (None, None),
    ],
)
def test_profile_nickname(kakao_server, account, expected):
    body = {"id": 77}
    if account is not None:
        body["kakao_account"] = account
    kakao_server.routes[USER_ME] = (200, body, 0)

    assert main.kakao_profile_nickname("tok", "77") == expected
    method, path, headers = kakao_server.requests[-1]
    assert (method, path) == ("GET", USER_ME)
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded;charset=utf-8"


def test_profile_for_another_member_is_unavailable(kakao_server):
    kakao_server.routes[USER_ME] = (200, {"id": 78, "kakao_account": {"profile": {"nickname": "남"}}}, 0)

    with pytest.raises(main.KakaoUnavailable):
        main.kakao_profile_nickname("tok", "77")


def test_unlink_posts_with_the_token(kakao_server):
    kakao_server.routes[UNLINK] = (200, {"id": 77}, 0)

    assert main.kakao_unlink("tok") is None
    method, path, headers = kakao_server.requests[-1]
    assert (method, path) == ("POST", UNLINK)
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded;charset=utf-8"

    kakao_server.routes[UNLINK] = (401, {"code": -401}, 0)
    with pytest.raises(main.KakaoTokenRejected):
        main.kakao_unlink("tok")


def test_kakao_login_and_withdraw_end_to_end_against_a_fake_kakao_server(
    client, kakao_server, monkeypatch
):
    monkeypatch.setattr(main, "KAKAO_APP_ID", 1234)
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 31337, "expires_in": 43199, "app_id": 1234}, 0)
    kakao_server.routes[USER_ME] = (200, {"id": 31337, "kakao_account": {"profile": {"nickname": "끝까지"}}}, 0)
    kakao_server.routes[UNLINK] = (200, {"id": 31337}, 0)

    login = kakao_login(client, "real-looking-token")
    assert login.status_code == 200, login.text
    assert login.json()["user"]["nickname"] == "끝까지"

    left = withdraw(client, login.json()["access_token"], {"kakao_access_token": "reauth-token"})
    assert left.status_code == 200, left.text
    assert [(m, p) for m, p, _ in kakao_server.requests] == [
        ("GET", TOKEN_INFO),
        ("GET", USER_ME),
        ("GET", TOKEN_INFO),
        ("POST", UNLINK),
    ]
    assert kakao_server.requests[-1][2]["Authorization"] == "Bearer reauth-token"
    assert count("users") == 0


# --- 고정 설정·토큰 노출 (변이 검사가 찾은 빈틈 — 다른 테스트는 이 값을 바꿔 끼움) ------------


def test_kakao_transport_constants():
    assert main.KAKAO_API_BASE == "https://kapi.kakao.com"
    assert main.KAKAO_CALL_TIMEOUT_SECONDS == 5.0
    assert main.KAKAO_MAX_CONCURRENT_CALLS == 10


def test_kakao_client_verifies_tls(kakao_server, monkeypatch):
    # 인증서 검증을 끄면 중간자가 토큰 정보(아무 회원번호 + 우리 앱 ID)를 꾸며 남의 계정으로 들어옵니다.
    seen = {}
    real_client = httpx.AsyncClient

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(main.httpx, "AsyncClient", spy)
    kakao_server.routes[TOKEN_INFO] = (200, {"id": 1, "app_id": 1234}, 0)

    main.kakao_token_info("tok")

    context = seen["verify"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert seen["trust_env"] is False


@pytest.mark.parametrize(
    "route",
    [(500, b"<html>", 0), (400, {"code": -1}, 0), (401, {"code": -401}, 0)],
    ids=["5xx", "kakao-outage", "rejected"],
)
def test_real_call_errors_never_carry_the_token(client, kakao_server, monkeypatch, capsys, route):
    monkeypatch.setattr(main, "KAKAO_APP_ID", 1234)
    secret = "kakao-secret-token-xyz"
    kakao_server.routes[TOKEN_INFO] = route

    kakao_login(client, secret)
    with pytest.raises((main.KakaoUnavailable, main.KakaoTokenRejected)) as raised:
        main.kakao_token_info(secret)

    assert secret not in str(raised.value)
    assert secret not in capsys.readouterr().err


def test_connection_failure_never_carries_the_token(monkeypatch):
    with ThreadingHTTPServer(("127.0.0.1", 0), _FakeKakaoHandler) as closed:
        port = closed.server_port
    monkeypatch.setattr(main, "KAKAO_API_BASE", f"http://127.0.0.1:{port}")

    with pytest.raises(main.KakaoUnavailable) as raised:
        main.kakao_token_info("kakao-secret-token-xyz")

    assert "kakao-secret-token-xyz" not in str(raised.value)
