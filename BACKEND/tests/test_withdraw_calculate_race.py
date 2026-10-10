"""탈퇴와 겹친 탄소 계산(DECISIONS 161) — 이력을 저장하려는 순간 계정이 없어졌으면 500 이 아니라 401.

계약은 docs/SCAN_API_CONTRACT.md 2-3 '탈퇴와 겹친 탄소 계산'과 BACKEND/API_CONTRACT.md 의 POST /api/carbon/calculate.
탈퇴는 users 행을 잠근 채 지우므로, 그동안 계산의 이력 INSERT 는 외래 키 확인에서 기다렸다가 탈퇴 커밋 뒤 걸린다.
반대로 계산이 먼저 넣었으면 탈퇴가 잠금에서 기다렸다가 그 이력까지 지운다.
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

import database
import main
from auth_helpers import signup

PASSWORD = "password123"
CALCULATION = {"materials": {"cotton": 100}, "weight_grams": 200}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def calculate(client, token):
    return client.post("/api/carbon/calculate", json=CALCULATION, headers=auth(token))


def withdraw(client, token):
    return client.post("/auth/withdraw", json={"password": PASSWORD}, headers=auth(token))


def table_counts():
    with database.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM access_tokens), "
                "(SELECT count(*) FROM analysis_results)"
            )
        ).one()


def two_devices(client, email):
    signup(client, email)
    return login(client, email), login(client, email)


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
    with database.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
        ).scalar_one()


def _run_while_paused(pause_prefix, first, second):
    """first 가 pause_prefix 로 시작하는 SQL 을 실행한 직후 멈추게 하고, second 가 잠금에서 기다리는 것을 본 뒤 푼다."""
    reached, release, listener = _pause_on(pause_prefix)
    out = {}
    try:
        leading = threading.Thread(target=lambda: out.setdefault("first", first()))
        leading.start()
        assert reached.wait(10)
        waiting = threading.Thread(target=lambda: out.setdefault("second", second()))
        waiting.start()
        deadline = time.monotonic() + 10
        while _backends_waiting_on_a_lock() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _backends_waiting_on_a_lock() >= 1
        release.set()
        leading.join(30)
        waiting.join(30)
    finally:
        release.set()
        event.remove(database.engine, "after_cursor_execute", listener)
    return out["first"], out["second"]


def test_calculation_waiting_on_a_withdrawal_is_401_and_saves_nothing(client):
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, tablet = two_devices(server, "leaving@example.com")

    # 탈퇴가 users 를 지우고 커밋하기 전에 멈춘 사이(users 행 잠금을 쥔 채) 다른 기기가 계산합니다.
    left, calculated = _run_while_paused(
        "DELETE FROM users", lambda: withdraw(server, phone), lambda: calculate(server, tablet)
    )

    assert left.status_code == 200, left.text
    assert calculated.status_code == 401, calculated.text
    body = calculated.json()
    assert body["status"] == "error"
    assert body["error_code"] == "AUTH_REQUIRED"
    assert body["message"] == "로그인이 만료되었습니다."
    assert table_counts() == (0, 0, 0)


def test_calculation_that_saved_first_is_200_and_the_withdrawal_removes_it(client):
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, tablet = two_devices(server, "staying-a-moment@example.com")

    # 계산이 이력을 넣고 커밋하기 전에 멈춘 사이 다른 기기가 탈퇴합니다 — 탈퇴는 users 행 잠금에서 기다립니다.
    calculated, left = _run_while_paused(
        "INSERT INTO analysis_results",
        lambda: calculate(server, tablet),
        lambda: withdraw(server, phone),
    )

    assert calculated.status_code == 200, calculated.text
    assert left.status_code == 200, left.text
    assert table_counts() == (0, 0, 0)


@pytest.fixture()
def account_removed_before_saving(monkeypatch):
    """토큰 확인을 통과한 뒤, 이력을 넣기 직전에 다른 연결이 계정을 지운 것처럼 만든다(탈퇴 커밋)."""

    def remove_then_build(materials, db, _original=main.build_emission_factors):
        with database.engine.begin() as connection:
            connection.execute(text("DELETE FROM access_tokens"))
            connection.execute(text("DELETE FROM users"))
        return _original(materials, db)

    monkeypatch.setattr(main, "build_emission_factors", remove_then_build)


def test_account_removed_after_the_token_check_is_401(client, account_removed_before_saving):
    signup(client, "gone@example.com")
    token = login(client, "gone@example.com")

    response = calculate(client, token)

    assert response.status_code == 401, response.text
    assert response.json()["message"] == "로그인이 만료되었습니다."
    assert table_counts() == (0, 0, 0)


def test_other_integrity_errors_stay_500(client, monkeypatch, account_removed_before_saving):
    # 401 로 바꾸는 것은 이력의 users 외래 키뿐입니다 — 다른 무결성 오류를 '로그인 만료'로 숨기지 않습니다.
    monkeypatch.setattr(main, "_integrity_constraint_name", lambda error: "some_other_constraint")
    server = TestClient(main.app, raise_server_exceptions=False)
    signup(server, "other@example.com")
    token = login(server, "other@example.com")

    assert calculate(server, token).status_code == 500
