"""DB 연결 풀 크기(DECISIONS 167): 느린 요청이 요청 스레드를 다 채워도 다른 요청이 연결을 받는다."""

import threading
import time

import anyio
import anyio.to_thread

import database
import main

PASSWORD = "password123"


def _request_thread_count() -> int:
    async def tokens():
        return anyio.to_thread.current_default_thread_limiter().total_tokens

    return anyio.run(tokens)


def test_pool_can_give_every_request_thread_a_connection():
    assert database.engine.pool.size() == database.DB_POOL_SIZE
    assert database.DB_POOL_SIZE + database.DB_MAX_OVERFLOW >= _request_thread_count()


def test_requests_get_a_connection_while_logins_hold_theirs_during_hashing(client, monkeypatch):
    # 기본 풀(15)에서는 해시 중인 로그인 15개가 연결을 다 쥐어, 16번째 로그인은 해시에 닿지 못하고
    # 다른 요청은 연결을 기다리다 30초 뒤 500 이었습니다. 스레드 하나만 남기고 로그인으로 채웁니다.
    logins = _request_thread_count() - 1
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", logins + 1)
    stored_hash = main.hash_password(PASSWORD)
    with database.SessionLocal() as db:
        # 가입 API 대신 DB 에 바로 넣습니다 — 이 시험은 가입 절차와 상관없습니다.
        db.add_all(
            database.User(email=f"pool-{i}@example.com", nickname="tester", password_hash=stored_hash)
            for i in range(logins)
        )
        db.commit()

    entered = []
    entered_lock = threading.Lock()
    release = threading.Event()
    verify_password = main.verify_password

    def held_verify(password, password_hash):
        with entered_lock:
            entered.append(1)
        release.wait(timeout=60)
        return verify_password(password, password_hash)

    monkeypatch.setattr(main, "verify_password", held_verify)
    statuses = []

    def login(i):
        response = client.post(
            "/auth/login", json={"email": f"pool-{i}@example.com", "password": PASSWORD}
        )
        statuses.append(response.status_code)

    threads = [threading.Thread(target=login, args=(i,)) for i in range(logins)]
    other = []
    other_thread = threading.Thread(target=lambda: other.append(client.get("/materials")))
    try:
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 15
        while len(entered) < logins and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(entered) == logins
        # 지금은 해시 동안 연결을 쥡니다(167 ⓓ-2 보류) — 놓게 바꾸면 이 줄을 고칩니다.
        assert database.engine.pool.checkedout() >= logins

        other_thread.start()
        other_thread.join(timeout=5)
        assert not other_thread.is_alive()
        assert other[0].status_code == 200
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=60)
        if other_thread.ident is not None:
            other_thread.join(timeout=60)

    assert statuses == [200] * logins
