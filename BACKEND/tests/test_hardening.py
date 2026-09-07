"""전면 점검(2026-08-29)에서 확정된 결함들의 회귀 테스트."""

import threading
from datetime import timedelta

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
