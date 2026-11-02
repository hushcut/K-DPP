"""옷장 서버 백업(DECISIONS 100·242) — GET·POST /me/closet.

계약은 BACKEND/API_CONTRACT.md 의 GET·POST /me/closet 절, 설계 전문은 docs/옷장백업-설계안.md(로컬).
서버는 옷 내용을 해석하지 않고 사용자당 한 행에 그대로 둔다. 내용이 같으면 200 changed=false, 다르고
base_version 이 지금 version 과 다르면 409, 그 밖에는 version +1(폰 우선).
"""

import json
import threading
import time
import tracemalloc
from datetime import timedelta

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError

import database
import main
from auth_helpers import signup

PASSWORD = "password123"
CLOSET_REVISION = "a28c2a50b363"
SOCIAL_REVISION = "19b7eee3b75c"
# 옷 제목에 넣어 로그·오류 문장에 옷 내용이 새는지 보는 표식.
MARKER = "옷장표식-7f3a"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"], response.json()["user"]["id"]


def account(client, email="closet@example.com"):
    assert signup(client, email).status_code == 200
    return login(client, email)


def get_closet(client, token):
    return client.get("/me/closet", headers=auth(token))


def save_closet(client, token, user_id, base_version, items):
    return client.post(
        "/me/closet",
        json={"user_id": user_id, "base_version": base_version, "items": items},
        headers=auth(token),
    )


def post_raw(client, token, body: str):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers.update(auth(token))
    return client.post("/me/closet", content=body.encode("utf-8"), headers=headers)


def rows(sql, **params):
    with database.engine.connect() as connection:
        return connection.execute(text(sql), params).all()


def snapshot_rows():
    return rows("SELECT user_id, version, item_count, items FROM closet_snapshots ORDER BY user_id")


def clothes(title, **extra):
    """앱 Clothes.toJson 과 같은 칸의 옷 한 벌."""
    item = {
        "title": title,
        "category": "상의",
        "health": 100,
        "materials": {"면": 60.0, "폴리에스터": 40.0},
        "careInstruction": "30도 물세탁\n건조기 금지",
        "carbonFootprint": 1.46,
        "carbonFootprintSource": "server",
        "carbonFootprintMin": None,
        "carbonFootprintMax": None,
        "minWeightGram": None,
        "maxWeightGram": None,
        "savedResultId": 7,
        "registeredAt": "2026-10-14T16:55:23.328586",
        "weightSource": "type_average",
        "calculationScope": "소재 생산",
        "calculationBasis": "소재별 배출계수 × 무게",
        "calculationSource": "K-DPP 소재별 배출계수 표(추정값)",
        "calculationNote": None,
    }
    item.update(extra)
    return item


def nested_items(depth):
    """items 배열을 1단으로 세어 가장 깊은 객체가 depth 단에 오는 items."""
    inner = {}
    for _ in range(depth - 2):
        inner = {"k": inner}
    return [inner]


# --- 조회·저장 기본 ---------------------------------------------------------------


def test_get_without_backup_is_version_zero(client):
    token, user_id = account(client)

    response = get_closet(client, token)

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "user_id": user_id,
        "version": 0,
        "item_count": 0,
        "items": [],
        "updated_at": None,
    }


def test_first_save_then_get_returns_the_same_items(client):
    token, user_id = account(client)
    items = [
        clothes("첫 옷 👕"),
        clothes(
            "둘째",
            materials={"_sa_instance_state": 50.0, "울": 50.0},
            careInstruction="NUL\u0000 줄바꿈\n탭\t이모지 🧺",
            carbonFootprint=15.0,
            savedResultId=None,
            registeredAt=None,
        ),
        {"title": "모르는 칸이 더 있는 새 앱의 옷", "nested": {"a": [1, {"b": None}]}},
    ]

    saved = save_closet(client, token, user_id, 0, items)

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "success"
    assert body["version"] == 1
    assert body["changed"] is True
    assert body["item_count"] == 3
    assert body["updated_at"].endswith("+00:00")

    fetched = get_closet(client, token)
    assert fetched.status_code == 200
    got = fetched.json()
    # 배열 순서·한글·이모지·null·중첩·'_sa' 로 시작하는 키·NUL·줄바꿈이 그대로 돌아옵니다.
    assert got["items"] == items
    assert got == {
        "status": "success",
        "user_id": user_id,
        "version": 1,
        "item_count": 3,
        "items": items,
        "updated_at": body["updated_at"],
    }
    # 15.0 은 15 로 바뀌지 않습니다(앱의 double 칸).
    assert '"carbonFootprint":15.0' in fetched.text
    assert snapshot_rows()[0][:3] == (user_id, 1, 3)


def test_changes_raise_the_version_and_stale_base_conflicts(client):
    token, user_id = account(client)
    assert save_closet(client, token, user_id, 0, [clothes("a")]).json()["version"] == 1

    second = save_closet(client, token, user_id, 1, [clothes("a"), clothes("b")])
    assert second.status_code == 200
    assert second.json()["version"] == 2

    stale = save_closet(client, token, user_id, 1, [clothes("c")])

    assert stale.status_code == 409
    body = stale.json()
    assert body["error_code"] == "CLOSET_VERSION_CONFLICT"
    assert body["message"] == "다른 기기에서 옷장 백업이 바뀌었습니다."
    assert body["detail"]["current_version"] == 2
    assert [row[:3] for row in snapshot_rows()] == [(user_id, 2, 2)]
    assert [item["title"] for item in get_closet(client, token).json()["items"]] == ["a", "b"]

    # 받은 current_version 으로 다시 보내면 폰 우선으로 덮습니다.
    retry = save_closet(client, token, user_id, 2, [clothes("c")])
    assert retry.status_code == 200
    assert retry.json()["version"] == 3


def test_same_content_is_a_no_op_whatever_the_base(client):
    token, user_id = account(client)
    items = [clothes("a")]
    first = save_closet(client, token, user_id, 0, items).json()

    again = save_closet(client, token, user_id, 99, items)

    assert again.status_code == 200
    assert again.json() == {
        "status": "success",
        "version": 1,
        "changed": False,
        "item_count": 1,
        "updated_at": first["updated_at"],
    }
    assert [row[:3] for row in snapshot_rows()] == [(user_id, 1, 1)]


def test_empty_closet_without_a_backup_creates_no_row(client):
    token, user_id = account(client)

    response = save_closet(client, token, user_id, 0, [])

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "version": 0,
        "changed": False,
        "item_count": 0,
        "updated_at": None,
    }
    assert snapshot_rows() == []


def test_emptying_a_backed_up_closet_is_a_change(client):
    token, user_id = account(client)
    save_closet(client, token, user_id, 0, [clothes("a")])

    emptied = save_closet(client, token, user_id, 1, [])

    assert emptied.status_code == 200
    assert emptied.json()["version"] == 2
    assert emptied.json()["changed"] is True
    assert get_closet(client, token).json()["items"] == []


def test_each_account_sees_only_its_own_backup(client):
    token_a, user_a = account(client, "a@example.com")
    token_b, user_b = account(client, "b@example.com")
    save_closet(client, token_a, user_a, 0, [clothes("A 의 옷")])

    assert get_closet(client, token_b).json()["items"] == []
    assert get_closet(client, token_b).json()["user_id"] == user_b
    assert get_closet(client, token_a).json()["items"][0]["title"] == "A 의 옷"


# --- 주인 대조·인증 ---------------------------------------------------------------


def test_body_user_id_must_match_the_token_user(client, capsys):
    token, user_id = account(client)
    capsys.readouterr()

    response = save_closet(client, token, user_id + 1, 0, [clothes(MARKER)])

    assert response.status_code == 403
    assert response.json()["error_code"] == "CLOSET_OWNER_MISMATCH"
    assert response.json()["message"] == "로그인한 계정의 옷장이 아닙니다."
    assert snapshot_rows() == []
    err = capsys.readouterr().err
    assert f"[closet] rejected user={user_id} reason=owner_mismatch items=1" in err
    assert MARKER not in err


def test_closet_needs_a_valid_session(client):
    token, user_id = account(client)
    expired, _ = login(client, "closet@example.com")
    revoked, _ = login(client, "closet@example.com")
    with database.engine.begin() as connection:
        connection.execute(
            text("UPDATE access_tokens SET expires_at = :t WHERE token = :h"),
            {"t": database.utc_now() - timedelta(seconds=1), "h": main.hash_access_token(expired)},
        )
    assert client.post("/auth/logout", headers=auth(revoked)).status_code == 200
    body = {"user_id": user_id, "base_version": 0, "items": []}

    for headers in ({}, {"Authorization": "Basic abc"}, auth("not-a-token"), auth(expired), auth(revoked)):
        assert client.get("/me/closet", headers=headers).status_code == 401, headers
        response = client.post("/me/closet", json=body, headers=headers)
        assert response.status_code == 401, headers
        assert response.json()["error_code"] == "AUTH_REQUIRED"

    # 세션 확인이 모양 검사보다 먼저입니다(501벌이어도 토큰이 없으면 401).
    too_many = {"user_id": user_id, "base_version": 0, "items": [{}] * (main.MAX_CLOSET_ITEMS + 1)}
    assert client.post("/me/closet", json=too_many).status_code == 401
    assert client.post("/me/closet", json={"items": "x"}).status_code == 401
    assert get_closet(client, token).status_code == 200


# --- 크기·모양 상한 ---------------------------------------------------------------


def test_item_count_limit_is_413_closet_too_large(client, capsys):
    token, user_id = account(client)
    limit = main.MAX_CLOSET_ITEMS

    at_limit = save_closet(client, token, user_id, 0, [{"n": i} for i in range(limit)])
    capsys.readouterr()
    over_limit = save_closet(client, token, user_id, 1, [{"n": i} for i in range(limit + 1)])

    assert at_limit.status_code == 200
    assert at_limit.json()["item_count"] == limit
    assert over_limit.status_code == 413
    body = over_limit.json()
    assert body["error_code"] == "CLOSET_TOO_LARGE"
    assert body["message"] == main.CLOSET_TOO_LARGE_MESSAGE
    assert body["detail"]["reason"] == "too_many_items"
    assert body["detail"]["max_items"] == limit
    assert "[closet] rejected reason=too_many_items" in capsys.readouterr().err
    assert snapshot_rows()[0][2] == limit


def test_item_count_limit_wins_over_other_shape_errors(client):
    token, _ = account(client)

    response = client.post(
        "/me/closet", json={"items": ["not-an-object"] * 600}, headers=auth(token)
    )

    assert response.status_code == 413
    assert response.json()["detail"]["reason"] == "too_many_items"


def test_many_items_stop_at_the_limit_without_building_every_error(client):
    # 원소 오류를 다 만든 뒤에 개수를 보면 요청 한 건이 메모리를 크게 올립니다(DECISIONS 242·244).
    token, user_id = account(client)
    body = json.dumps({"user_id": user_id, "base_version": 0, "items": [1] * 200_000})
    assert len(body) <= main.MAX_JSON_REQUEST_BYTES

    tracemalloc.start()
    started = time.monotonic()
    try:
        response = post_raw(client, token, body)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert response.status_code == 413
    assert response.json()["detail"]["reason"] == "too_many_items"
    assert time.monotonic() - started < 1
    assert peak < 25 * 1024 * 1024


def test_serialized_size_limit_is_413_not_the_image_message(client):
    token, user_id = account(client)
    room = main.MAX_CLOSET_BYTES - len('[{"t":""}]')

    at_limit = save_closet(client, token, user_id, 0, [{"t": "x" * room}])
    over_limit = save_closet(client, token, user_id, 1, [{"t": "x" * (room + 1)}])
    # 한글은 UTF-8 3바이트로 셉니다.
    korean = save_closet(client, token, user_id, 1, [{"t": "가" * (room // 3 + 1)}])

    assert at_limit.status_code == 200, at_limit.text
    for response in (over_limit, korean):
        assert response.status_code == 413
        body = response.json()
        assert body["error_code"] == "CLOSET_TOO_LARGE"
        assert body["detail"]["reason"] == "too_many_bytes"
        assert body["detail"]["max_bytes"] == 524_288
        assert "이미지" not in body["message"]
    assert snapshot_rows()[0][1] == 1


def test_depth_limit(client):
    token, user_id = account(client)

    eight = save_closet(client, token, user_id, 0, nested_items(main.MAX_CLOSET_DEPTH))
    nine = save_closet(client, token, user_id, 1, nested_items(main.MAX_CLOSET_DEPTH + 1))

    assert eight.status_code == 200, eight.text
    assert get_closet(client, token).status_code == 200
    assert nine.status_code == 422
    assert nine.json()["error_code"] == "CLOSET_INVALID"
    assert nine.json()["detail"]["reason"] == "too_deep"
    assert snapshot_rows()[0][1] == 1


@pytest.mark.parametrize("depth", [1200, 5000])
def test_very_deep_json_is_rejected_before_saving(client, depth):
    # 서버의 JSON 해석(C 구현)은 수천 단도 받아서, 깊이 검사가 없으면 저장된 뒤 응답을 만드는
    # 파이썬 재귀 직렬화에서 터질 수 있었습니다. 스택으로 세어 저장 전에 막습니다.
    token, user_id = account(client)
    deep = '{"k":' * (depth - 1) + "{}" + "}" * (depth - 1)
    body = f'{{"user_id":{user_id},"base_version":0,"items":[{deep}]}}'

    response = post_raw(client, token, body)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["reason"] == "too_deep"
    assert snapshot_rows() == []
    assert get_closet(client, token).status_code == 200


@pytest.mark.parametrize(
    ("literal", "reason"),
    [
        ("NaN", "invalid_number"),
        ("Infinity", "invalid_number"),
        ("-Infinity", "invalid_number"),
        ("1e400", "invalid_number"),
        ('"\\ud800"', "invalid_unicode"),
    ],
)
def test_values_that_cannot_be_stored_are_422(client, literal, reason):
    token, user_id = account(client)
    body = f'{{"user_id":{user_id},"base_version":0,"items":[{{"v":{literal}}}]}}'

    response = post_raw(client, token, body)

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "CLOSET_INVALID"
    assert response.json()["detail"]["reason"] == reason
    assert snapshot_rows() == []


def test_lone_surrogate_in_a_key_is_422(client):
    token, user_id = account(client)
    body = f'{{"user_id":{user_id},"base_version":0,"items":[{{"\\udfff":1}}]}}'

    response = post_raw(client, token, body)

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "invalid_unicode"


@pytest.mark.parametrize(
    "body",
    [
        {"base_version": 0, "items": []},
        {"user_id": "USER", "items": []},
        {"user_id": "USER", "base_version": -1, "items": []},
        {"user_id": "USER", "base_version": "0", "items": []},
        {"user_id": "USER", "base_version": 1.5, "items": []},
        {"user_id": "USER", "base_version": 0, "items": {"a": 1}},
        {"user_id": "USER", "base_version": 0, "items": ["옷장표식-7f3a"]},
        {"user_id": "USER", "base_version": 0},
    ],
)
def test_shape_errors_are_422_without_echoing_input(client, body):
    token, user_id = account(client)
    body = {key: (user_id if value == "USER" else value) for key, value in body.items()}

    response = client.post("/me/closet", json=body, headers=auth(token))

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    assert MARKER not in response.text
    assert snapshot_rows() == []


def test_string_user_id_is_rejected(client):
    token, user_id = account(client)

    response = client.post(
        "/me/closet",
        json={"user_id": str(user_id), "base_version": 0, "items": []},
        headers=auth(token),
    )

    assert response.status_code == 422


def test_broken_json_is_422_before_the_session_check(client):
    response = post_raw(client, None, '{"user_id": 1, "items": [')

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


# --- 탈퇴 ------------------------------------------------------------------------


def test_withdraw_deletes_the_backup(client):
    token, user_id = account(client)
    other_token, other_id = account(client, "other@example.com")
    save_closet(client, token, user_id, 0, [clothes("a")])
    save_closet(client, other_token, other_id, 0, [clothes("b")])

    response = client.post("/auth/withdraw", json={"password": PASSWORD}, headers=auth(token))

    assert response.status_code == 200
    assert [row[0] for row in snapshot_rows()] == [other_id]


def test_withdraw_with_a_revoked_token_keeps_the_backup(client):
    token, user_id = account(client)
    revoked, _ = login(client, "closet@example.com")
    save_closet(client, token, user_id, 0, [clothes("a")])
    client.post("/auth/logout", headers=auth(revoked))

    response = client.post("/auth/withdraw", json={"password": PASSWORD}, headers=auth(revoked))

    assert response.status_code == 401
    assert [row[:2] for row in snapshot_rows()] == [(user_id, 1)]


# --- 경합(users 잠금 — DECISIONS 161 과 같은 방식) ---------------------------------


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


def test_save_waiting_on_a_withdrawal_is_401_and_saves_nothing(client):
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, user_id = account(server)
    tablet, _ = login(server, "closet@example.com")

    # 탈퇴가 users 를 지우고 커밋하기 전에 멈춘 사이(users 행 잠금을 쥔 채) 다른 기기가 옷장을 올립니다.
    left, saved = _run_while_paused(
        "DELETE FROM users",
        lambda: server.post("/auth/withdraw", json={"password": PASSWORD}, headers=auth(phone)),
        lambda: save_closet(server, tablet, user_id, 0, [clothes("a")]),
    )

    assert left.status_code == 200, left.text
    assert saved.status_code == 401, saved.text
    assert saved.json()["message"] == "로그인이 만료되었습니다."
    assert snapshot_rows() == []
    assert rows("SELECT count(*) FROM users") == [(0,)]


def test_save_that_wrote_first_is_200_and_the_withdrawal_removes_it(client):
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, user_id = account(server)
    tablet, _ = login(server, "closet@example.com")

    # 저장이 행을 넣고 커밋하기 전에 멈춘 사이 다른 기기가 탈퇴합니다 — 탈퇴는 users 잠금에서 기다립니다.
    saved, left = _run_while_paused(
        "INSERT INTO closet_snapshots",
        lambda: save_closet(server, tablet, user_id, 0, [clothes("a")]),
        lambda: server.post("/auth/withdraw", json={"password": PASSWORD}, headers=auth(phone)),
    )

    assert saved.status_code == 200, saved.text
    assert left.status_code == 200, left.text
    assert snapshot_rows() == []
    assert rows("SELECT count(*) FROM users") == [(0,)]


@pytest.mark.parametrize("same_content", [True, False])
def test_two_first_uploads_of_one_account_never_500(client, same_content):
    server = TestClient(main.app, raise_server_exceptions=False)
    phone, user_id = account(server)
    tablet, _ = login(server, "closet@example.com")
    second_items = [clothes("a")] if same_content else [clothes("b")]

    first, second = _run_while_paused(
        "INSERT INTO closet_snapshots",
        lambda: save_closet(server, phone, user_id, 0, [clothes("a")]),
        lambda: save_closet(server, tablet, user_id, 0, second_items),
    )

    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    if same_content:
        assert second.status_code == 200, second.text
        assert second.json()["changed"] is False
        assert second.json()["version"] == 1
    else:
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["current_version"] == 1
    assert [row[:2] for row in snapshot_rows()] == [(user_id, 1)]


# --- 로그·DB 오류 문장 -------------------------------------------------------------


def test_success_and_no_op_leave_no_log_and_conflicts_leave_no_content(client, capsys):
    token, user_id = account(client)
    capsys.readouterr()

    save_closet(client, token, user_id, 0, [clothes(MARKER)])
    save_closet(client, token, user_id, 0, [clothes(MARKER)])
    assert "[closet]" not in capsys.readouterr().err

    save_closet(client, token, user_id, 0, [clothes(MARKER + "-2")])
    save_closet(client, token, user_id, 1, nested_items(main.MAX_CLOSET_DEPTH + 1))
    err = capsys.readouterr().err
    assert f"[closet] conflict user={user_id} base=0 current=1" in err
    assert f"[closet] rejected user={user_id} reason=too_deep items=1" in err
    assert MARKER not in err


def _insert_snapshot_directly(user_id, version, item_count, items):
    with pytest.raises(IntegrityError) as raised:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO closet_snapshots (user_id, version, item_count, items, created_at, updated_at) "
                    "VALUES (:u, :v, :c, :items, now(), now())"
                ),
                {"u": user_id, "v": version, "c": item_count, "items": items},
            )
    return str(raised.value)


def test_db_errors_do_not_carry_closet_content(client):
    token, user_id = account(client)
    assert database.engine.hide_parameters is True
    long_items = MARKER + "x" * 200 + "끝표식"

    # 외래 키 위반: SQLAlchemy 매개변수는 숨겨지고 PostgreSQL 문장에도 키만 나옵니다.
    message = _insert_snapshot_directly(999_999, 1, 0, long_items)
    assert "SQL parameters hidden" in message
    assert MARKER not in message

    # CHECK 둘은 alembic check 가 비교하지 않아 직접 넣어 봅니다. 이 위반은 PostgreSQL 이 'Failing row
    # contains' 에 칸마다 앞 64바이트까지 싣지만, 옷장 코드는 version 0·음수 개수를 쓰지 않아 API 로는
    # 닿지 않습니다(받아들인 한계 — 계약 문서). 64바이트를 넘는 뒷부분은 실리지 않습니다.
    for version, item_count in ((0, 0), (1, -1)):
        message = _insert_snapshot_directly(user_id, version, item_count, long_items)
        assert "SQL parameters hidden" in message
        assert "끝표식" not in message
    assert snapshot_rows() == []


# --- 리비전 ----------------------------------------------------------------------


def test_closet_revision_downgrade_refuses_while_backups_exist(alembic_config):
    command.upgrade(alembic_config, CLOSET_REVISION)
    with database.engine.begin() as connection:
        user_id = connection.execute(
            text(
                "INSERT INTO users (email, nickname, password_hash, created_at) "
                "VALUES ('rev@example.com', 'rev', 'hash', now()) RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO closet_snapshots (user_id, version, item_count, items, created_at, updated_at) "
                "VALUES (:u, 1, 0, '[]', now(), now())"
            ),
            {"u": user_id},
        )

    with pytest.raises(RuntimeError, match="옷장 백업 1개"):
        command.downgrade(alembic_config, SOCIAL_REVISION)
    assert rows("SELECT version_num FROM alembic_version") == [(CLOSET_REVISION,)]
    assert rows("SELECT count(*) FROM closet_snapshots") == [(1,)]

    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM closet_snapshots"))
    command.downgrade(alembic_config, SOCIAL_REVISION)

    assert "closet_snapshots" not in inspect(database.engine).get_table_names()
    assert rows("SELECT version_num FROM alembic_version") == [(SOCIAL_REVISION,)]
    assert rows("SELECT email FROM users") == [("rev@example.com",)]
