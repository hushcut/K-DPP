"""전면 점검(2026-08-29)에서 확정된 결함들의 회귀 테스트."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

import database
import main


def _login_token(client, email="hardening@example.com"):
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "tester"},
    )
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    return login.json()["access_token"]


def test_nan_material_ratio_is_rejected(client):
    # NaN은 모든 대소 비교가 False라 검증을 통과해 500을 내던 결함.
    response = client.post(
        "/analyze",
        content='{"materials": {"cotton": NaN}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "MATERIAL_RATIO_INVALID"


def test_nan_weight_is_rejected(client):
    token = _login_token(client)
    response = client.post(
        "/api/carbon/calculate",
        content='{"materials": {"cotton": 100}, "weight_grams": NaN}',
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "WEIGHT_INVALID"


def test_huge_weight_is_rejected(client):
    token = _login_token(client)
    response = client.post(
        "/api/carbon/calculate",
        json={"materials": {"cotton": 100}, "weight_grams": 1e308},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "WEIGHT_INVALID"


def test_password_with_surrounding_whitespace_is_rejected(client):
    # 가입은 strip 저장, 로그인은 원문 검증이라 영구 로그인 불가가 되던 결함.
    response = client.post(
        "/auth/signup",
        json={
            "email": "space@example.com",
            "password": "password1 ",
            "nickname": "space-user",
        },
    )

    assert response.status_code == 400


def test_invalid_email_format_is_rejected(client):
    response = client.post(
        "/auth/signup",
        json={"email": "@.", "password": "password123", "nickname": "tester"},
    )

    assert response.status_code == 400


def test_expired_token_returns_401_instead_of_anonymous_save(client):
    token = _login_token(client)

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
        "/analyze",
        json={"materials": {"cotton": 100}},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 만료 토큰이 익명 저장(200)으로 조용히 넘어가지 않아야 합니다.
    assert response.status_code == 401


def test_scan_flags_partial_ratio(client):
    token = _login_token(client)
    response = client.post(
        "/api/scan",
        files={"image": ("label.jpg", b"test-image", "image/jpeg")},
        data={"raw_ocr_text": "COTTON 50% POLYESTER 30%"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["ai_success"] is False
    assert body["analysis_failure_reason"] == "RATIO_INCOMPLETE"


def test_scan_rejects_missing_content_type(client):
    token = _login_token(client)
    response = client.post(
        "/api/scan",
        files={"image": ("label.bin", b"test-image", "")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 415


def test_oversized_upload_returns_413(client, monkeypatch):
    # run_ocr가 없으면 크기 검사 전에 503이 나므로 스텁으로 대체합니다.
    monkeypatch.setattr(main, "run_ocr", lambda *a, **k: "COTTON 100%")

    token = _login_token(client)
    big = b"x" * (main.MAX_UPLOAD_BYTES + 1)
    response = client.post(
        "/api/scan",
        files={"image": ("big.jpg", big, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_access_token_is_stored_hashed(client):
    token = _login_token(client, email="hash-check@example.com")

    session = database.SessionLocal()
    try:
        # 원문 그대로 저장된 행이 없어야 하고, 해시로 저장된 행은 있어야 합니다.
        raw_row = (
            session.query(database.AccessToken)
            .filter(database.AccessToken.token == token)
            .first()
        )
        hashed_row = (
            session.query(database.AccessToken)
            .filter(database.AccessToken.token == main.hash_access_token(token))
            .first()
        )
    finally:
        session.close()

    assert raw_row is None
    assert hashed_row is not None

    # 원문 토큰으로는 여전히 정상 인증되어야 합니다.
    history = client.get(
        "/me/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert history.status_code == 200


def test_login_locks_after_repeated_failures(client):
    email = "lockout@example.com"
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "lock-user"},
    )

    for _ in range(main.LOGIN_MAX_ATTEMPTS):
        response = client.post(
            "/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert response.status_code == 401

    # 잠금 이후에는 올바른 비밀번호로도 잠시 로그인할 수 없어야 합니다.
    locked = client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert locked.status_code == 429
    assert locked.json()["error_code"] == "TOO_MANY_ATTEMPTS"


def test_login_success_resets_failure_count(client):
    email = "reset-count@example.com"
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "reset-user"},
    )

    for _ in range(main.LOGIN_MAX_ATTEMPTS - 1):
        client.post("/auth/login", json={"email": email, "password": "nope-nope"})

    ok = client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert ok.status_code == 200

    # 성공으로 카운터가 초기화되어 다음 실패 1회로는 잠기지 않아야 합니다.
    after = client.post(
        "/auth/login", json={"email": email, "password": "nope-nope"}
    )
    assert after.status_code == 401


def test_oversized_upload_rejected_even_with_raw_ocr_text(client):
    # raw_ocr_text를 함께 보내는 것만으로 용량 제한을 우회할 수 없어야 합니다.
    token = _login_token(client, email="bypass@example.com")
    big = b"x" * (main.MAX_UPLOAD_BYTES + 1)
    response = client.post(
        "/api/scan",
        files={"image": ("big.jpg", big, "image/jpeg")},
        data={"raw_ocr_text": "COTTON 100%"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_wrong_content_type_rejected_even_with_raw_ocr_text(client):
    token = _login_token(client, email="bypass2@example.com")
    response = client.post(
        "/api/scan",
        files={"image": ("label.txt", b"not-image", "text/plain")},
        data={"raw_ocr_text": "COTTON 100%"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 415


def test_malformed_authorization_header_returns_401(client):
    # 'Basic ...'나 빈 Bearer는 익명이 아니라 형식 오류(401)로 알려야 합니다.
    for bad_header in ("Basic abc", "Bearer ", "not-a-scheme"):
        response = client.post(
            "/analyze",
            json={"materials": {"cotton": 100}},
            headers={"Authorization": bad_header},
        )
        assert response.status_code == 401, bad_header

    # 헤더가 아예 없으면 기존대로 익명 계산이 허용됩니다.
    anonymous = client.post("/analyze", json={"materials": {"cotton": 100}})
    assert anonymous.status_code == 200


def test_concurrent_login_failures_are_all_counted(client):
    # 조회-갱신이 원자적이지 않으면 동시 실패 횟수가 유실돼 잠금이 늦어집니다.
    email = "race@example.com"
    threads = [
        threading.Thread(target=main.record_login_failure, args=(email,))
        for _ in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    count, _ = main._login_failures[email]
    assert count == 20


def test_chunked_oversized_body_returns_413(client):
    # Content-Length 없는 chunked 전송도 수신 바이트 기준으로 차단돼야 합니다.
    def body_stream():
        chunk = b"x" * (1024 * 1024)
        for _ in range(main.MAX_REQUEST_BYTES // len(chunk) + 2):
            yield chunk

    response = client.post(
        "/analyze",
        content=body_stream(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "PAYLOAD_TOO_LARGE"


def test_stale_low_count_login_failures_are_pruned(client):
    from datetime import timedelta as _td

    stale_time = database.utc_now() - _td(seconds=main.LOGIN_FAILURE_TTL_SECONDS + 1)
    with main._login_failures_lock:
        main._login_failures["old@example.com"] = (2, stale_time)

    # 새 실패를 기록하는 순간 만료된 저횟수 기록이 청소돼야 합니다.
    main.record_login_failure("new@example.com")

    with main._login_failures_lock:
        assert "old@example.com" not in main._login_failures
        assert "new@example.com" in main._login_failures


def test_login_failure_entries_are_capped(client, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_FAILURES_MAX_ENTRIES", 5)

    for i in range(20):
        main.record_login_failure(f"cap-{i}@example.com")

    with main._login_failures_lock:
        # 새 항목 1개가 더해지기 전 기준으로 상한을 정리하므로 상한+1 이하입니다.
        assert len(main._login_failures) <= 6


# --- 입력 상한과 조회 상한 (2026-09-07 개선 조사에서 확정) ---------------------


def test_analyze_rejects_too_many_materials_without_echoing_input(client):
    """소재 개수 제한이 없으면 무인증 요청 1건으로 워커를 오래 점유할 수 있었다.

    거부 응답이 입력을 되돌려주면 큰 요청이 큰 응답으로 증폭되므로 그것도 함께 막는다.
    """
    materials = {f"material{i}": 100.0 / 5000 for i in range(5000)}

    response = client.post("/analyze", json={"materials": materials})

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"
    # 입력이 5,000개여도 응답은 짧게 유지돼야 한다.
    assert len(response.content) < 2000


def test_analyze_rejects_overlong_material_name(client):
    response = client.post(
        "/analyze",
        json={"materials": {"a" * (main.MAX_MATERIAL_NAME_LENGTH + 1): 100}},
    )

    assert response.status_code == 422


def test_carbon_calculate_rejects_overlong_raw_ocr_text(client):
    token = _login_token(client, "ocrlimit@example.com")

    over_limit = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 100},
            "weight_grams": 200,
            "raw_ocr_text": "x" * (main.MAX_RAW_OCR_TEXT_LENGTH + 1),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    within_limit = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 100},
            "weight_grams": 200,
            "raw_ocr_text": "x" * main.MAX_RAW_OCR_TEXT_LENGTH,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert over_limit.status_code == 422
    assert within_limit.status_code == 200


def test_normal_material_input_still_calculates(client):
    """상한을 넣으면서 정상 입력의 계산 결과가 달라지면 안 된다."""
    response = client.post(
        "/analyze",
        json={"materials": {"cotton": 60, "polyester": 40}},
    )

    assert response.status_code == 200
    # cotton 8.3 * 0.6 + polyester 9.5 * 0.4
    assert response.json()["carbon_footprint"] == 8.78


def test_material_lookup_reads_the_table_once_per_request(client):
    """소재 이름마다 전체 표를 다시 읽던 구조라 비용이 곱해졌다."""
    session = database.SessionLocal()
    try:
        index = main.load_material_index(session)
        # 별칭까지 모두 색인돼야 이전의 순회 검색과 결과가 같다.
        assert index["cotton"].name_en == "cotton"
        assert index["면"].name_en == "cotton"
        # 두 번째 호출은 같은 객체를 그대로 돌려준다(요청당 1회 조회).
        assert main.load_material_index(session) is index
    finally:
        session.close()


def test_me_history_is_capped_and_reports_more(client):
    token = _login_token(client, "historylimit@example.com")
    session = database.SessionLocal()
    try:
        user = (
            session.query(database.User)
            .filter(database.User.email == "historylimit@example.com")
            .first()
        )
        session.add_all(
            database.AnalysisResult(
                user_id=user.id,
                materials='{"cotton": 100.0}',
                carbon_footprint=1.46,
                unit="kg CO2eq",
                unknown_materials="[]",
            )
            for _ in range(main.MAX_HISTORY_ITEMS + 5)
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/me/history", headers={"Authorization": f"Bearer {token}"})
    body = response.json()

    assert response.status_code == 200
    assert len(body["history"]) == main.MAX_HISTORY_ITEMS
    assert body["has_more"] is True


def test_me_history_reports_no_more_when_under_the_cap(client):
    token = _login_token(client, "historysmall@example.com")

    response = client.get("/me/history", headers={"Authorization": f"Bearer {token}"})
    body = response.json()

    assert response.status_code == 200
    assert body["history"] == []
    assert body["has_more"] is False


# --- 비밀번호 해시 반복 수 (2026-10-04 보안 손질, DECISIONS 139) ---------------


def _legacy_hash(password, iterations=120_000):
    """반복 수를 올리기 전 형식 그대로 만든 해시."""
    salt = "legacy-salt-0001"
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _stored_hash(email):
    session = database.SessionLocal()
    try:
        return (
            session.query(database.User.password_hash)
            .filter(database.User.email == email)
            .scalar()
        )
    finally:
        session.close()


def _set_stored_hash(email, password_hash):
    session = database.SessionLocal()
    try:
        session.query(database.User).filter(database.User.email == email).update(
            {"password_hash": password_hash}
        )
        session.commit()
    finally:
        session.close()


def _signup(client, email):
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": "iter-user"},
    )


def test_signup_stores_hash_with_current_iterations(client):
    email = "iter-new@example.com"
    _signup(client, email)

    # OWASP 권장 하한(PBKDF2-HMAC-SHA256 60만 회)보다 낮아지면 안 됩니다.
    assert main.PASSWORD_HASH_ITERATIONS >= 600_000
    prefix = f"pbkdf2_sha256${main.PASSWORD_HASH_ITERATIONS}$"
    assert _stored_hash(email).startswith(prefix)
    # 미가입 이메일의 타이밍 가드도 같은 반복 수여야 응답 시간이 맞습니다.
    assert main.DUMMY_PASSWORD_HASH.startswith(prefix)


def test_login_upgrades_legacy_iteration_hash(client):
    email = "iter-legacy@example.com"
    _signup(client, email)
    _set_stored_hash(email, _legacy_hash("password123"))

    first = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert first.status_code == 200

    upgraded = _stored_hash(email)
    assert upgraded.startswith(f"pbkdf2_sha256${main.PASSWORD_HASH_ITERATIONS}$")
    assert main.verify_password("password123", upgraded)

    # 이미 지금 반복 수면 다시 쓰지 않고, 같은 비밀번호로 계속 로그인됩니다.
    second = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert second.status_code == 200
    assert _stored_hash(email) == upgraded


def test_failed_login_keeps_legacy_hash(client):
    email = "iter-wrong@example.com"
    _signup(client, email)
    legacy = _legacy_hash("password123")
    _set_stored_hash(email, legacy)

    response = client.post("/auth/login", json={"email": email, "password": "wrong-password"})

    assert response.status_code == 401
    assert _stored_hash(email) == legacy


def test_rehash_does_not_undo_a_concurrent_password_change(client, monkeypatch):
    email = "iter-race@example.com"
    _signup(client, email)
    _set_stored_hash(email, _legacy_hash("password123"))
    changed = main.hash_password("brand-new-pass1")
    original_verify = main.verify_password

    def verify_then_change(password, stored_hash):
        ok = original_verify(password, stored_hash)
        # 로그인이 옛 해시를 검증한 직후 다른 요청의 비밀번호 변경이 먼저 커밋된 상황.
        _set_stored_hash(email, changed)
        return ok

    monkeypatch.setattr(main, "verify_password", verify_then_change)
    response = client.post("/auth/login", json={"email": email, "password": "password123"})

    assert response.status_code == 200
    assert _stored_hash(email) == changed


# --- CORS (2026-10-04 보안 손질, DECISIONS 139) ---------------------------------


def _cors_middleware():
    return next(m for m in main.app.user_middleware if m.cls is CORSMiddleware)


def test_parse_cors_origins():
    assert main.parse_cors_origins(None) == []
    assert main.parse_cors_origins("") == []
    assert main.parse_cors_origins(" http://localhost:5000/ , ,https://a.example") == [
        "http://localhost:5000",
        "https://a.example",
    ]


def test_cors_allows_no_origin_by_default(client):
    simple = client.get("/", headers={"Origin": "https://evil.example"})
    assert simple.status_code == 200
    assert "access-control-allow-origin" not in simple.headers

    preflight = client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_cors_configured_origin_can_call_the_api():
    # 미들웨어는 import 때 정해지므로, main 의 CORS 설정에 출처만 넣은 같은 미들웨어로 감싸
    # 허용 메서드·헤더가 실제 요청(Bearer 토큰·JSON POST)에 충분한지 본다.
    allowed = "http://localhost:5000"
    cors = _cors_middleware()
    browser = TestClient(
        CORSMiddleware(main.app, **{**cors.kwargs, "allow_origins": [allowed]})
    )

    preflight = browser.options(
        "/auth/login",
        headers={
            "Origin": allowed,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == allowed

    simple = browser.get("/", headers={"Origin": allowed})
    assert simple.headers["access-control-allow-origin"] == allowed

    other = browser.get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_cors_stays_outside_the_body_size_limit():
    # 바깥층이어야 413 응답에도 CORS 헤더가 붙는다(user_middleware 는 바깥층부터).
    classes = [m.cls for m in main.app.user_middleware]
    assert classes.index(CORSMiddleware) < classes.index(main.BodySizeLimitMiddleware)


# --- 로그인 IP 기준 (2026-10-04 보안 손질, DECISIONS 139) -------------------------


def _count_hashes(monkeypatch, delay=0.0):
    calls = []
    original_verify = main.verify_password

    def counting_verify(password, stored_hash):
        calls.append(1)
        if delay:
            time.sleep(delay)
        return original_verify(password, stored_hash)

    monkeypatch.setattr(main, "verify_password", counting_verify)
    return calls


def _try_login(client, email, password="wrong-password"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_ip_limit_blocks_rotating_emails(client, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 3)
    hashes = _count_hashes(monkeypatch)
    _signup(client, "ip-victim@example.com")

    for i in range(3):
        assert _try_login(client, f"ip-spray-{i}@example.com").status_code == 401

    # 처음 보는 이메일이라 이메일 잠금엔 안 걸리지만 IP 한도에 걸리고, 해시까지 가지 않습니다.
    blocked = _try_login(client, "ip-spray-9@example.com")
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert "15분 후" in blocked.json()["message"]
    # 같은 IP 면 맞는 비밀번호여도 창이 끝날 때까지 막힙니다.
    assert _try_login(client, "ip-victim@example.com", "password123").status_code == 429
    assert len(hashes) == 3


def test_successful_logins_do_not_count_toward_ip_limit(client, monkeypatch):
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 2)
    email = "ip-ok@example.com"
    _signup(client, email)

    for _ in range(4):
        assert _try_login(client, email, "password123").status_code == 200
    assert _try_login(client, email).status_code == 401
    # 실패는 1번뿐이라 아직 한도(2) 아래입니다.
    assert _try_login(client, email, "password123").status_code == 200


def test_concurrent_login_burst_hashes_only_up_to_the_ip_limit(client, monkeypatch):
    # 실패를 해시가 끝난 뒤에 세면, 동시에 몰아친 요청이 모두 검사를 통과해 해시까지 갑니다.
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 3)
    hashes = _count_hashes(monkeypatch, delay=0.3)
    statuses = []

    def attempt(i):
        statuses.append(_try_login(client, f"burst-{i}@example.com").status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [401] * 3 + [429] * 5
    assert len(hashes) == 3


def test_login_ip_failure_window_expires(client):
    stale = database.utc_now() - timedelta(seconds=main.LOGIN_IP_WINDOW_SECONDS + 1)
    with main._login_failures_lock:
        main._login_ip_failures["testclient"] = (main.LOGIN_IP_MAX_FAILURES, stale)

    assert _try_login(client, "after-window@example.com").status_code == 401
    with main._login_failures_lock:
        assert main._login_ip_failures["testclient"][0] == 1


def test_client_ip_key_groups_ipv6_by_64_prefix():
    assert main.client_ip_key("8.8.8.8") == "8.8.8.8"
    assert main.client_ip_key("::ffff:8.8.8.8") == "8.8.8.8"
    same_64 = main.client_ip_key("2001:4860:1:2:aaaa::1")
    assert same_64 == "2001:4860:1:2::/64"
    assert main.client_ip_key("2001:4860:1:2:bbbb:cccc:dddd:2") == same_64
    assert main.client_ip_key("2001:4860:1:3::1") != same_64
    assert main.client_ip_key("testclient") == "testclient"
    assert main.client_ip_key(None) is None


def test_client_ip_key_skips_non_public_addresses():
    # Docker·프록시가 접속 주소를 가리면 모두가 게이트웨이 주소(리허설에서 172.19.0.1)로
    # 보입니다. 그 주소 하나로 모두를 함께 막지 않도록 IP 기준을 건너뜁니다.
    for host in ("172.19.0.1", "127.0.0.1", "10.0.0.5", "192.168.0.10", "::1", "fd00::1"):
        assert main.client_ip_key(host) is None, host


# --- 가입 IP 기준 (2026-10-04 보안 손질, DECISIONS 142) ---------------------------


def _count_signup_hashes(monkeypatch, delay=0.0):
    calls = []
    original_hash = main.hash_password

    def counting_hash(password):
        calls.append(1)
        if delay:
            time.sleep(delay)
        return original_hash(password)

    monkeypatch.setattr(main, "hash_password", counting_hash)
    return calls


def _try_signup(client, email, password="password123", nickname="ip-user"):
    return client.post(
        "/auth/signup",
        json={"email": email, "password": password, "nickname": nickname},
    )


def test_signup_ip_limit_counts_successes_and_conflicts(client, monkeypatch):
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 3)
    hashes = _count_signup_hashes(monkeypatch)

    assert _try_signup(client, "signup-a@example.com").status_code == 200
    # 이미 가입된 이메일(409)은 그 이메일이 가입돼 있는지를 알려 주므로 셉니다.
    assert _try_signup(client, "signup-a@example.com").status_code == 409
    assert _try_signup(client, "signup-b@example.com").status_code == 200

    blocked = _try_signup(client, "signup-c@example.com")
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert blocked.json()["message"] == "가입 시도가 너무 많습니다. 60분 후 다시 시도해 주세요."
    # 가입 여부 조회(409)도 창이 끝날 때까지 막히고, 막힌 시도는 해시·계정 생성까지 가지 않습니다.
    assert _try_signup(client, "signup-a@example.com").status_code == 429
    assert len(hashes) == 2
    assert _try_login(client, "signup-c@example.com", "password123").status_code == 401


def test_signup_format_errors_do_not_count_toward_ip_limit(client, monkeypatch):
    # 형식 오류(400)는 DB·해시를 거치지 않으므로 세지 않습니다 — 입력 실수로 한도를 쓰지 않게.
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 1)

    assert _try_signup(client, "not-an-email").status_code == 400
    assert _try_signup(client, "short-nick@example.com", nickname="a").status_code == 400
    assert _try_signup(client, "short-pw@example.com", password="short").status_code == 400
    assert _try_signup(client, "format-ok@example.com").status_code == 200
    assert _try_signup(client, "format-next@example.com").status_code == 429


def test_concurrent_signup_burst_hashes_only_up_to_the_ip_limit(client, monkeypatch):
    # 해시가 끝난 뒤에 세면, 동시에 몰아친 가입이 모두 검사를 통과해 해시·계정 생성까지 갑니다.
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 3)
    hashes = _count_signup_hashes(monkeypatch, delay=0.3)
    statuses = []

    def attempt(i):
        statuses.append(_try_signup(client, f"signup-burst-{i}@example.com").status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200] * 3 + [429] * 5
    assert len(hashes) == 3


def test_signup_ip_window_expires(client):
    stale = database.utc_now() - timedelta(seconds=main.SIGNUP_IP_WINDOW_SECONDS + 1)
    with main._login_failures_lock:
        main._signup_ip_attempts["testclient"] = (main.SIGNUP_IP_MAX_ATTEMPTS, stale)

    assert _try_signup(client, "signup-after-window@example.com").status_code == 200
    with main._login_failures_lock:
        assert main._signup_ip_attempts["testclient"][0] == 1


def test_signup_and_login_ip_limits_are_counted_separately(client, monkeypatch):
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(main, "LOGIN_IP_MAX_FAILURES", 1)
    email = "separate@example.com"

    assert _try_signup(client, email).status_code == 200
    # 가입 시도는 로그인 실패로 세지 않습니다.
    assert _try_login(client, email, "password123").status_code == 200
    assert _try_login(client, email).status_code == 401
    blocked_login = _try_login(client, email)
    assert blocked_login.status_code == 429
    assert blocked_login.json()["message"].startswith("로그인 시도가")
    # 로그인 실패도 가입 시도로 세지 않습니다.
    assert _try_signup(client, "separate-2@example.com").status_code == 200
    blocked_signup = _try_signup(client, "separate-3@example.com")
    assert blocked_signup.status_code == 429
    assert blocked_signup.json()["message"].startswith("가입 시도가")


def test_signup_ip_limit_uses_the_same_ip_key_as_login(client, monkeypatch):
    # IPv6 는 /64 대역으로 묶고, 공인 주소가 아니면(게이트웨이·사설) 건너뜁니다.
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 1)
    first = TestClient(main.app, client=("2001:4860:1:2::1", 50000))
    same_64 = TestClient(main.app, client=("2001:4860:1:2:ffff::9", 50000))
    other = TestClient(main.app, client=("8.8.4.4", 50000))
    gateway = TestClient(main.app, client=("172.19.0.1", 50000))

    assert _try_signup(first, "v6-a@example.com").status_code == 200
    assert _try_signup(same_64, "v6-b@example.com").status_code == 429
    assert _try_signup(other, "v4-a@example.com").status_code == 200
    for i in range(3):
        assert _try_signup(gateway, f"gateway-{i}@example.com").status_code == 200


# --- API 문서 끄기 (2026-10-04 보안 손질, DECISIONS 142) ----------------------------

API_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def test_parse_api_docs_enabled():
    for value in (None, "", "  ", "on", "TRUE", "1"):
        assert main.parse_api_docs_enabled(value) is True, value
    for value in ("off", "False", " 0 "):
        assert main.parse_api_docs_enabled(value) is False, value
    # 알 수 없는 값은 켬으로 넘기지 않고 시작을 막습니다(배포 설정 오타 대비).
    for value in ("disable", "no", "offf"):
        with pytest.raises(ValueError):
            main.parse_api_docs_enabled(value)


def test_api_docs_are_on_by_default(client):
    for path in API_DOC_PATHS:
        assert client.get(path).status_code == 200, path


_API_DOCS_PROBE = """
import json
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
print(json.dumps({p: client.get(p).status_code for p in ("/", "/docs", "/redoc", "/openapi.json")}))
"""


def _import_main_with_api_docs(value):
    # 앱 객체는 import 때 만들어지므로 환경변수를 바꾼 별도 프로세스에서 봅니다.
    return subprocess.run(
        [sys.executable, "-c", _API_DOCS_PROBE],
        cwd=Path(main.__file__).parent,
        env=dict(os.environ, K_DPP_API_DOCS=value),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_api_docs_can_be_turned_off():
    result = _import_main_with_api_docs("off")
    assert result.returncode == 0, result.stderr
    statuses = json.loads(result.stdout.strip().splitlines()[-1])
    # 상태 확인(compose healthcheck)이 부르는 / 는 그대로입니다.
    assert statuses == {"/": 200, "/docs": 404, "/redoc": 404, "/openapi.json": 404}


def test_unknown_api_docs_value_stops_startup():
    result = _import_main_with_api_docs("disable")
    assert result.returncode != 0
    assert "K_DPP_API_DOCS" in result.stderr
