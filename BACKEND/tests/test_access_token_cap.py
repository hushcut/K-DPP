"""로그인 토큰 상한(DECISIONS 160) — 계정마다 최근 ACCESS_TOKENS_PER_USER_MAX 개, 만료 토큰은 새 토큰을 만들 때 지움.

계약은 BACKEND/API_CONTRACT.md 의 'POST /auth/login'·'변경 이력 — 로그인 토큰 상한'과 docs/SCAN_API_CONTRACT.md 2-1.
카카오 로그인의 같은 상한은 test_kakao_login.py 에서 봅니다. 실제 로그인을 여러 번 하는 테스트는 해시 횟수를
줄이려고 상한을 3 으로 줄이고, 상한 10 자체는 토큰을 DB 에 직접 넣어 봅니다.
"""

import secrets
import threading
import time
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, text

import database
import main
from auth_helpers import signup

PASSWORD = "password123"


def login_response(client, email):
    return client.post("/auth/login", json={"email": email, "password": PASSWORD})


def login(client, email):
    response = login_response(client, email)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def history_status(client, token):
    return client.get("/me/history", headers={"Authorization": f"Bearer {token}"}).status_code


def scalar(sql, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def user_id(email):
    return scalar("SELECT id FROM users WHERE email = :email", email=email)


def token_count(uid):
    return scalar("SELECT count(*) FROM access_tokens WHERE user_id = :uid", uid=uid)


def insert_tokens(uid, ages_minutes, expires_in=timedelta(days=1)):
    """토큰을 DB 에 직접 넣고 원문을 돌려준다 — ages_minutes 는 만든 지 몇 분 전인지, expires_in=None 은 만료 시각 없음."""
    now = database.utc_now()
    raws = []
    with database.engine.begin() as connection:
        for age in ages_minutes:
            raw = secrets.token_urlsafe(32)
            connection.execute(
                text(
                    "INSERT INTO access_tokens (token, user_id, created_at, expires_at) "
                    "VALUES (:token, :uid, :created_at, :expires_at)"
                ),
                {
                    "token": main.hash_access_token(raw),
                    "uid": uid,
                    "created_at": now - timedelta(minutes=age),
                    "expires_at": None if expires_in is None else now + expires_in,
                },
            )
            raws.append(raw)
    return raws


def test_login_keeps_only_the_newest_ten_tokens(client):
    assert main.ACCESS_TOKENS_PER_USER_MAX == 10  # 계약 숫자(API_CONTRACT 'POST /auth/login')
    signup(client, "cap@example.com")
    uid = user_id("cap@example.com")
    devices = insert_tokens(uid, range(10, 0, -1))  # 10분 전 … 1분 전, devices[0] 이 가장 오래됨

    new_device = login(client, "cap@example.com")

    assert token_count(uid) == 10
    assert history_status(client, devices[0]) == 401
    for token in devices[1:] + [new_device]:
        assert history_status(client, token) == 200


def test_real_logins_push_out_the_first_device(client, monkeypatch):
    monkeypatch.setattr(main, "ACCESS_TOKENS_PER_USER_MAX", 3)
    signup(client, "devices@example.com")

    sessions = [login(client, "devices@example.com") for _ in range(4)]

    assert token_count(user_id("devices@example.com")) == 3
    assert history_status(client, sessions[0]) == 401
    for token in sessions[1:]:
        assert history_status(client, token) == 200


def test_expired_tokens_are_removed_first_and_take_no_slot(client, monkeypatch):
    monkeypatch.setattr(main, "ACCESS_TOKENS_PER_USER_MAX", 3)
    signup(client, "expired-cap@example.com")
    uid = user_id("expired-cap@example.com")
    alive = insert_tokens(uid, [30, 20])
    # 살아 있는 토큰보다 나중에 만든 만료 토큰·만료 시각 없는 토큰 — 남겨 두면 최근 자리를 차지합니다.
    insert_tokens(uid, [10], expires_in=timedelta(seconds=-1))
    insert_tokens(uid, [5], expires_in=None)

    new_device = login(client, "expired-cap@example.com")

    assert token_count(uid) == 3
    for token in alive + [new_device]:
        assert history_status(client, token) == 200


def test_another_accounts_newer_tokens_do_not_push_yours_out(client):
    signup(client, "busy@example.com")
    signup(client, "quiet@example.com")
    busy, quiet = user_id("busy@example.com"), user_id("quiet@example.com")
    insert_tokens(busy, range(1, 11))  # 다른 계정의 더 최근 토큰 10개
    mine = insert_tokens(quiet, range(100, 91, -1))  # 내 오래된 토큰 9개

    new_device = login(client, "quiet@example.com")

    assert (token_count(busy), token_count(quiet)) == (10, 10)
    for token in mine + [new_device]:
        assert history_status(client, token) == 200


def _pause_on(statement_prefix):
    reached, release, armed = threading.Event(), threading.Event(), [True]

    def listener(conn, cursor, statement, parameters, context, executemany):
        if armed[0] and statement.startswith(statement_prefix):
            armed[0] = False
            reached.set()
            release.wait(10)

    event.listen(database.engine, "after_cursor_execute", listener)
    return reached, release, listener


def _backends_waiting_on_a_lock():
    return scalar(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )


def test_concurrent_logins_of_one_account_stay_within_the_cap(client, monkeypatch):
    # 토큰을 만드는 쪽이 users 행을 잠근 채 정리하므로, 같은 계정의 두 로그인은 차례로 정리됩니다.
    monkeypatch.setattr(main, "ACCESS_TOKENS_PER_USER_MAX", 3)
    email = "together@example.com"
    signup(client, email)
    uid = user_id(email)
    insert_tokens(uid, [30, 20, 10])
    server = TestClient(main.app, raise_server_exceptions=False)
    # 첫 로그인이 오래된 토큰을 지우고 새 토큰을 넣은 뒤, 커밋하기 전에 멈춥니다(users 행 잠금을 쥔 채).
    reached, release, listener = _pause_on("INSERT INTO access_tokens")
    out = {}
    try:
        first = threading.Thread(
            target=lambda: out.setdefault("first", login_response(server, email))
        )
        first.start()
        assert reached.wait(10)
        second = threading.Thread(
            target=lambda: out.setdefault("second", login_response(server, email))
        )
        second.start()
        # 두 번째 로그인이 잠금에서 기다리는 것을 본 뒤 풉니다(비밀번호 확인 해시가 끝나야 거기 닿음).
        deadline = time.monotonic() + 10
        while _backends_waiting_on_a_lock() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _backends_waiting_on_a_lock() >= 1
        release.set()
        first.join(30)
        second.join(30)
    finally:
        release.set()
        event.remove(database.engine, "after_cursor_execute", listener)

    assert out["first"].status_code == 200, out["first"].text
    assert out["second"].status_code == 200, out["second"].text
    assert token_count(uid) == 3
    for response in out.values():
        assert history_status(client, response.json()["access_token"]) == 200
