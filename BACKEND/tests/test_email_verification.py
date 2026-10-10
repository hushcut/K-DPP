"""이메일 인증번호·비밀번호 찾기(DECISIONS 144·147·148)."""

import hashlib
import hmac
import threading
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import auth_helpers
import database
import main
from auth_helpers import fix_next_code, latest_email, request_code, signup
from process_helpers import run_python


def _request(client, email, purpose="signup"):
    return client.post("/auth/email-code", json={"email": email, "purpose": purpose})


def _reset(client, email, code, new_password="newpassword123"):
    return client.post(
        "/auth/password-reset",
        json={"email": email, "code": code, "new_password": new_password},
    )


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _wrong(code):
    return "000000" if code != "000000" else "111111"


def _user_count():
    session = database.SessionLocal()
    try:
        return session.query(database.User).count()
    finally:
        session.close()


def _count_hashes(monkeypatch):
    calls = []
    original_hash = main.hash_password

    def counting_hash(password):
        calls.append(1)
        return original_hash(password)

    monkeypatch.setattr(main, "hash_password", counting_hash)
    return calls


# --- 번호 요청: 가입 여부 숨기기 -------------------------------------------------


def test_email_code_response_is_the_same_whether_registered_or_not(client, monkeypatch):
    assert signup(client, "member@example.com").status_code == 200
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    auth_helpers.SENT_EMAILS.clear()

    for purpose in ("signup", "password_reset"):
        member = _request(client, "member@example.com", purpose)
        stranger = _request(client, "stranger@example.com", purpose)
        assert member.status_code == stranger.status_code == 200
        assert member.json() == stranger.json()

    # 응답은 같고, 보내는 메일만 다릅니다.
    assert latest_email("stranger@example.com", "signup").code is not None
    notice = latest_email("member@example.com", "signup")
    assert notice.code is None
    assert "비밀번호 찾기" in notice.body
    assert latest_email("member@example.com", "password_reset").code is not None
    assert latest_email("stranger@example.com", "password_reset") is None
    # 번호 기록은 네 경우 모두 똑같이 만듭니다(이어지는 가입·재설정 응답으로도 드러나지 않게).
    assert set(main._email_codes) == {
        ("signup", "member@example.com"),
        ("signup", "stranger@example.com"),
        ("password_reset", "member@example.com"),
        ("password_reset", "stranger@example.com"),
    }


def test_email_code_response_body_by_purpose(client):
    assert _request(client, "a@example.com").json() == {
        "status": "success",
        "message": "인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.",
        "expires_in": 600,
        "resend_after": 60,
    }
    assert _request(client, "b@example.com", "password_reset").json() == {
        "status": "success",
        "message": "가입된 이메일이면 인증번호를 보냈습니다. 메일이 오지 않으면 주소를 확인해 주세요.",
        "expires_in": 600,
        "resend_after": 60,
    }


def test_email_code_normalizes_email(client):
    code = request_code(client, "  Mixed.Case@Example.COM ")
    assert ("signup", "mixed.case@example.com") in main._email_codes
    assert signup(client, "mixed.case@example.com", code=code).status_code == 200


def test_email_code_rejects_bad_email_and_purpose(client):
    bad_email = _request(client, "not-an-email")
    assert bad_email.status_code == 400
    assert bad_email.json()["error_code"] == "BAD_REQUEST"
    too_long = "a" * 243 + "@example.com"  # 255자 — 요청 모델의 상한(422)
    assert _request(client, too_long).status_code == 422
    # 원문은 254자지만 소문자로 바꾸면 256자(İ → i + 윗점)라 정규화한 값의 상한(400)에 걸립니다.
    grows = "İİ" + "a" * 240 + "@example.com"
    assert len(grows) == main.MAX_EMAIL_LENGTH
    assert _request(client, grows).status_code == 400
    assert _request(client, "a" * 242 + "@example.com").status_code == 200  # 254자

    for body in (
        {"email": "p@example.com"},
        {"email": "p@example.com", "purpose": "login"},
        {"email": "p@example.com", "purpose": None},
    ):
        response = client.post("/auth/email-code", json=body)
        assert response.status_code == 422, body
        assert response.json()["error_code"] == "VALIDATION_ERROR"
    # 거절된 요청은 번호도 한도도 만들지 않습니다.
    assert ("signup", "p@example.com") not in main._email_codes
    assert "p@example.com" not in main._email_code_senders


# --- 가입: 번호 확인 -------------------------------------------------------------


def test_signup_without_code_field_is_422(client):
    response = client.post(
        "/auth/signup",
        json={"email": "old-app@example.com", "password": "password123", "nickname": "tester"},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_signup_without_requested_code_requires_resend(client):
    response = signup(client, "no-code@example.com", code="123456")
    assert response.status_code == 400
    assert response.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"


def test_wrong_codes_count_down_then_the_code_is_discarded(client):
    email = "count-down@example.com"
    code = request_code(client, email)
    wrong = _wrong(code)

    for remaining in (4, 3):
        response = signup(client, email, code=wrong)
        assert response.status_code == 400
        assert response.json()["error_code"] == "VERIFICATION_CODE_INVALID"
        assert response.json()["detail"]["remaining_attempts"] == remaining
        assert f"{remaining}번 더" in response.json()["message"]

    # 숫자 6자리가 아니면 형식 오류이고 틀린 횟수에 넣지 않습니다.
    for malformed in ("12345", "1234567", "12a456", "", "١٢٣٤٥٦"):
        response = signup(client, email, code=malformed)
        assert response.status_code == 400, malformed
        assert response.json()["error_code"] == "BAD_REQUEST"
        assert response.json()["message"] == "인증번호 6자리를 입력해 주세요."

    for remaining in (2, 1):
        assert signup(client, email, code=wrong).json()["detail"]["remaining_attempts"] == remaining
    fifth = signup(client, email, code=wrong)
    assert fifth.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"
    # 버려진 번호는 맞는 번호여도 쓸 수 없습니다.
    late = signup(client, email, code=code)
    assert late.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"
    assert _user_count() == 0


def test_code_with_surrounding_spaces_is_accepted(client):
    code = request_code(client, "spaces@example.com")
    assert signup(client, "spaces@example.com", code=f" {code} ").status_code == 200


def test_expired_code_requires_resend(client):
    email = "expired-code@example.com"
    code = request_code(client, email)
    with main._email_code_lock:
        main._email_codes[("signup", email)].expires_at = database.utc_now() - timedelta(seconds=1)

    response = signup(client, email, code=code)
    assert response.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"
    assert ("signup", email) not in main._email_codes


def test_new_code_replaces_the_previous_one(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    email = "replace@example.com"
    first = fix_next_code(monkeypatch, "111111")
    request_code(client, email)
    second = fix_next_code(monkeypatch, "222222")
    request_code(client, email)

    stale = signup(client, email, code=first)
    assert stale.json()["error_code"] == "VERIFICATION_CODE_INVALID"
    assert signup(client, email, code=second).status_code == 200


def test_code_is_bound_to_its_email_and_purpose(client, monkeypatch):
    code = fix_next_code(monkeypatch)
    request_code(client, "owner@example.com")

    other_email = signup(client, "someone-else@example.com", code=code)
    assert other_email.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"
    other_purpose = _reset(client, "owner@example.com", code)
    assert other_purpose.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"
    assert signup(client, "owner@example.com", code=code).status_code == 200


def test_signup_code_is_used_up_only_on_success(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    assert signup(client, "taken@example.com").status_code == 200
    code = fix_next_code(monkeypatch)
    request_code(client, "taken@example.com")

    # 번호를 409 보다 먼저 봅니다 — 틀린 번호로는 가입 여부(409)를 볼 수 없습니다.
    wrong = signup(client, "taken@example.com", code=_wrong(code))
    assert wrong.json()["error_code"] == "VERIFICATION_CODE_INVALID"
    # 409 로는 번호가 사라지지 않습니다.
    assert signup(client, "taken@example.com", code=code).status_code == 409
    assert signup(client, "taken@example.com", code=code).status_code == 409

    request_code(client, "fresh@example.com")
    assert signup(client, "fresh@example.com", code=code).status_code == 200
    # 가입에 성공한 번호는 다시 쓸 수 없습니다(409 가 아니라 다시 받기).
    reused = signup(client, "fresh@example.com", code=code)
    assert reused.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"


def test_signup_wrong_codes_count_toward_the_signup_ip_limit(client, monkeypatch):
    # 검사 순서: 형식 → 가입 IP 한도(142) → 번호. 틀린 번호도 IP 한도를 씁니다.
    monkeypatch.setattr(main, "SIGNUP_IP_MAX_ATTEMPTS", 2)
    hashes = _count_hashes(monkeypatch)
    email = "ip-guess@example.com"
    code = request_code(client, email)

    for _ in range(2):
        assert signup(client, email, code=_wrong(code)).json()["error_code"] == (
            "VERIFICATION_CODE_INVALID"
        )
    blocked = signup(client, email, code=code)
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert hashes == []


def test_concurrent_wrong_codes_cannot_exceed_the_failure_limit(client, monkeypatch):
    email = "race@example.com"
    code = request_code(client, email)
    original_digest = main._email_code_digest

    def slow_digest(*args):
        # 읽기와 틀린 수 증가 사이를 벌려, 잠금이 없으면 같은 횟수를 여럿이 읽게 합니다.
        time.sleep(0.05)
        return original_digest(*args)

    monkeypatch.setattr(main, "_email_code_digest", slow_digest)
    codes = []

    def attempt():
        codes.append(signup(client, email, code=_wrong(code)).json()["error_code"])

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(codes) == sorted(
        ["VERIFICATION_CODE_INVALID"] * 4 + ["VERIFICATION_CODE_RESEND_REQUIRED"] * 6
    )
    assert signup(client, email, code=code).json()["error_code"] == (
        "VERIFICATION_CODE_RESEND_REQUIRED"
    )


def test_codes_are_kept_only_as_hmac(client):
    email = "hmac@example.com"
    code = request_code(client, email)
    record = main._email_codes[("signup", email)]

    assert code not in repr(record)
    expected = hmac.new(
        main._EMAIL_CODE_KEY, f"signup\n{email}\n{code}".encode(), hashlib.sha256
    ).digest()
    assert record.digest == expected
    assert record.digest != hashlib.sha256(code.encode()).digest()


# --- 발송 한도 -------------------------------------------------------------------


def test_resend_is_blocked_for_60_seconds_across_purposes(client):
    email = "resend@example.com"
    code = request_code(client, email)

    for purpose in ("signup", "password_reset"):
        too_soon = _request(client, email, purpose)
        assert too_soon.status_code == 429
        body = too_soon.json()
        assert body["error_code"] == "EMAIL_CODE_RESEND_TOO_SOON"
        assert 1 <= body["detail"]["retry_after"] <= 60
        assert f"{body['detail']['retry_after']}초 후" in body["message"]
    # 막힌 요청은 이전 번호를 갈아 끼우지 않습니다.
    assert len(auth_helpers.SENT_EMAILS) == 1

    with main._email_code_lock:
        window = main._email_code_senders[email]
        window.last_requested_at -= timedelta(seconds=main.EMAIL_CODE_RESEND_SECONDS)
    assert _request(client, email, "password_reset").status_code == 200
    # 용도가 다르면 번호도 따로입니다 — 가입 번호는 그대로 살아 있습니다.
    assert signup(client, email, code=code).status_code == 200


def _shift_email_windows(email, hours):
    with main._email_code_lock:
        window = main._email_code_senders[email]
        shift = timedelta(hours=hours)
        window.hour_start -= shift
        window.day_start -= shift
        window.last_requested_at -= shift


def test_per_email_hourly_and_daily_limits(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    email = "limits@example.com"

    for i in range(5):
        purpose = ("signup", "password_reset")[i % 2]  # 두 용도 합산
        assert _request(client, email, purpose).status_code == 200
    hourly = _request(client, email)
    assert hourly.status_code == 429
    assert hourly.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert 3500 < hourly.json()["detail"]["retry_after"] <= 3600
    assert "1시간 후" in hourly.json()["message"]

    _shift_email_windows(email, hours=1)
    for _ in range(5):
        assert _request(client, email).status_code == 200
    # 1시간 5회와 24시간 10회에 함께 걸리면, 둘 다 풀리는 때(더 늦은 24시간 쪽)를 알려 줍니다.
    both = _request(client, email)
    assert both.status_code == 429
    assert 22 * 3600 < both.json()["detail"]["retry_after"] <= 23 * 3600
    assert "23시간 후" in both.json()["message"]
    _shift_email_windows(email, hours=1)
    # 1시간 창은 풀렸지만 24시간 10회에 닿았습니다. 첫 요청부터 24시간 = 약 22시간 남음.
    daily = _request(client, email)
    assert daily.status_code == 429
    assert daily.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert 21 * 3600 < daily.json()["detail"]["retry_after"] <= 22 * 3600
    assert "22시간 후" in daily.json()["message"]
    # 막힌 요청은 세지 않습니다.
    assert main._email_code_senders[email].day_count == 10


def test_ip_limit_counts_requests_across_emails(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_IP_HOURLY_MAX", 3)
    for i in range(3):
        assert _request(client, f"ip-{i}@example.com").status_code == 200

    blocked = _request(client, "ip-9@example.com")
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"
    assert 3500 < blocked.json()["detail"]["retry_after"] <= 3600

    # 다른 IP 는 따로 세고, 공인 주소가 아니면(게이트웨이·사설) IP 기준을 건너뜁니다.
    other = TestClient(main.app, client=("8.8.4.4", 50000))
    assert _request(other, "ip-other@example.com").status_code == 200
    gateway = TestClient(main.app, client=("172.19.0.1", 50000))
    for i in range(4):
        assert _request(gateway, f"gateway-{i}@example.com").status_code == 200


def _slow_send_window(monkeypatch):
    # 한도를 읽은 뒤·기록을 쓰기 전에 불리는 생성자를 늦춰, 잠금이 없으면 여럿이 같은 값을 읽게 합니다.
    original = main._EmailCodeSendWindow

    def slow(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "_EmailCodeSendWindow", slow)


def test_concurrent_requests_for_one_email_send_only_once(client, monkeypatch):
    _slow_send_window(monkeypatch)
    statuses = []

    def attempt():
        statuses.append(_request(client, "burst@example.com").status_code)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200] + [429] * 7
    assert len(auth_helpers.SENT_EMAILS) == 1


def test_concurrent_requests_cannot_exceed_the_ip_limit(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_IP_HOURLY_MAX", 3)
    _slow_send_window(monkeypatch)
    statuses = []

    def attempt(i):
        statuses.append(_request(client, f"ip-burst-{i}@example.com").status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200] * 3 + [429] * 5


def test_server_daily_cap_counts_every_accepted_request(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_DAILY_MAX", 2)

    # 가입 안 된 이메일의 비밀번호 찾기는 메일이 안 가지만 셉니다(가입 여부를 드러내지 않게).
    assert _request(client, "nobody@example.com", "password_reset").status_code == 200
    # 막힌 요청(429)은 세지 않습니다.
    assert _request(client, "nobody@example.com").status_code == 429
    assert _request(client, "second@example.com").status_code == 200

    capped = _request(client, "third@example.com")
    assert capped.status_code == 503
    assert capped.json()["error_code"] == "EMAIL_SEND_UNAVAILABLE"
    assert "retry_after" not in capped.json()["detail"]
    assert ("signup", "third@example.com") not in main._email_codes
    assert len(auth_helpers.SENT_EMAILS) == 1


def test_expired_records_are_pruned_but_a_fresh_resend_wait_is_kept(client):
    now = database.utc_now()
    long_ago = now - timedelta(days=2)
    with main._email_code_lock:
        main._email_codes[("signup", "old@example.com")] = main._EmailCode(
            digest=b"x", expires_at=now - timedelta(seconds=1)
        )
        main._email_code_senders["old@example.com"] = main._EmailCodeSendWindow(
            long_ago, long_ago, 5, long_ago, 10
        )
        # 24시간 창은 막 끝났지만 마지막 요청은 10초 전 — 재요청 대기는 남아야 합니다.
        day_edge = now - timedelta(seconds=main.EMAIL_CODE_DAY_SECONDS)
        main._email_code_senders["edge@example.com"] = main._EmailCodeSendWindow(
            now - timedelta(seconds=10), day_edge, 1, day_edge, 10
        )
        main._email_code_ip_requests["198.51.100.7"] = (20, long_ago)
        main._email_daily_requests[(now - timedelta(days=1)).date()] = 99

    assert _request(client, "new@example.com").status_code == 200
    assert ("signup", "old@example.com") not in main._email_codes
    assert "old@example.com" not in main._email_code_senders
    assert "198.51.100.7" not in main._email_code_ip_requests
    assert list(main._email_daily_requests) == [database.utc_now().date()]
    assert _request(client, "edge@example.com").json()["error_code"] == (
        "EMAIL_CODE_RESEND_TOO_SOON"
    )


# --- 비밀번호 찾기 ---------------------------------------------------------------


def test_password_reset_changes_password_and_logs_out_everywhere(client, monkeypatch):
    email = "forgot@example.com"
    assert signup(client, email).status_code == 200
    tokens = [_login(client, email, "password123").json()["access_token"] for _ in range(2)]
    # 이메일 로그인 잠금도 풀려야 합니다.
    for _ in range(main.LOGIN_MAX_ATTEMPTS):
        _login(client, email, "wrong-password")
    assert _login(client, email, "password123").status_code == 429

    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    code = request_code(client, email, "password_reset")
    response = _reset(client, email, code)

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요.",
    }
    for token in tokens:
        history = client.get("/me/history", headers={"Authorization": f"Bearer {token}"})
        assert history.status_code == 401
    assert _login(client, email, "newpassword123").status_code == 200
    assert _login(client, email, "password123").status_code == 401
    reused = _reset(client, email, code, "another-password")
    assert reused.json()["error_code"] == "VERIFICATION_CODE_RESEND_REQUIRED"


def test_password_reset_accepts_the_same_password(client):
    email = "same-pw@example.com"
    signup(client, email)
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")

    assert _reset(client, email, code, "password123").status_code == 200
    assert _login(client, email, "password123").status_code == 200


def test_password_reset_checks_format_before_the_code(client):
    email = "reset-format@example.com"
    signup(client, email)
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")

    assert _reset(client, "not-an-email", code).status_code == 400
    assert _reset(client, email, code, "short").status_code == 400
    assert _reset(client, email, code, " padded-password ").status_code == 400
    malformed = _reset(client, email, "12-456")
    assert malformed.status_code == 400
    assert malformed.json()["error_code"] == "BAD_REQUEST"
    missing = client.post("/auth/password-reset", json={"email": email, "code": code})
    assert missing.status_code == 422
    # 형식 오류는 틀린 횟수에 들어가지 않았습니다.
    assert _reset(client, email, _wrong(code)).json()["detail"]["remaining_attempts"] == 4
    assert _reset(client, email, code).status_code == 200


def _email_of_length(length):
    domain = "@example.com"
    return "a" * (length - len(domain)) + domain


def test_email_code_rejects_overlong_emails_before_counting(client):
    for email in (_email_of_length(main.MAX_EMAIL_LENGTH + 1), "x" * 1_000_000):
        response = _request(client, email)

        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"
        assert response.json()["detail"][0]["loc"] == ["body", "email"]
        # 거부 응답은 입력을 되돌려주지 않습니다(증폭 방지).
        assert len(response.content) < 2000

    # 핸들러 전에 막혀 번호·이메일 한도·IP 한도·하루 발송 상한 어디에도 남지 않습니다.
    assert main._email_codes == {}
    assert main._email_code_senders == {}
    assert main._email_code_ip_requests == {}
    assert main._email_daily_requests == {}

    # 상한 그대로는 받습니다(대조군).
    at_limit = _email_of_length(main.MAX_EMAIL_LENGTH)
    assert _request(client, at_limit).status_code == 200
    assert list(main._email_code_senders) == [at_limit]


def test_password_reset_rejects_overlong_inputs_without_using_the_code(client, monkeypatch):
    email = "reset-limit@example.com"
    signup(client, email)
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")
    hashes = _count_hashes(monkeypatch)

    for name, response in (
        ("email", _reset(client, _email_of_length(main.MAX_EMAIL_LENGTH + 1), code)),
        ("new_password", _reset(client, email, code, "p" * (main.MAX_PASSWORD_LENGTH + 1))),
        ("new_password", _reset(client, email, code, "p" * 1_000_000)),
    ):
        assert response.status_code == 422, name
        assert response.json()["error_code"] == "VALIDATION_ERROR", name
        assert response.json()["detail"][0]["loc"] == ["body", name]
        assert len(response.content) < 2000, name

    # 해시도 틀린 횟수도 없었고, 같은 번호로 상한 그대로의 새 비밀번호를 정할 수 있습니다.
    assert hashes == []
    assert _reset(client, email, _wrong(code)).json()["detail"]["remaining_attempts"] == 4
    at_limit = "p" * main.MAX_PASSWORD_LENGTH
    assert _reset(client, email, code, at_limit).status_code == 200
    assert client.post("/auth/login", json={"email": email, "password": at_limit}).status_code == 200


def test_password_reset_hashes_only_after_a_correct_code(client, monkeypatch):
    email = "reset-hash@example.com"
    signup(client, email)
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")
    hashes = _count_hashes(monkeypatch)

    assert _reset(client, email, _wrong(code)).json()["error_code"] == "VERIFICATION_CODE_INVALID"
    assert hashes == []
    assert _reset(client, email, code).status_code == 200
    assert len(hashes) == 1


def test_password_reset_does_not_reveal_whether_the_email_is_registered(client, monkeypatch):
    signup(client, "member@example.com")
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    code = fix_next_code(monkeypatch)
    for email in ("member@example.com", "stranger@example.com"):
        _request(client, email, "password_reset")

    member = _reset(client, "member@example.com", _wrong(code))
    stranger = _reset(client, "stranger@example.com", _wrong(code))
    assert member.status_code == stranger.status_code == 400
    assert member.json() == stranger.json()

    # 가입 안 된 이메일엔 번호가 가지 않지만, 번호를 맞혔다면 같은 성공 응답(계정은 생기지 않음).
    hashes = _count_hashes(monkeypatch)
    users_before = _user_count()
    guessed = _reset(client, "stranger@example.com", code)
    assert guessed.status_code == 200
    assert guessed.json()["message"] == "비밀번호를 다시 설정했습니다. 새 비밀번호로 로그인해 주세요."
    assert len(hashes) == 1
    assert _user_count() == users_before


# --- 발송(백그라운드)·설정 ------------------------------------------------------


def test_delivery_failure_does_not_change_the_response(client, monkeypatch, capsys):
    def broken(message):
        raise RuntimeError("mail service down")

    monkeypatch.setattr(main, "deliver_email", broken)
    response = _request(client, "broken@example.com")
    assert response.status_code == 200
    assert "인증 메일 처리 실패" in capsys.readouterr().err


def test_email_code_request_does_not_need_the_database(client, monkeypatch, capsys):
    # 요청 처리 중엔 DB 를 보지 않습니다(가입 여부 조회는 응답 뒤). DB 가 없어도 응답은 같습니다.
    def no_database():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(database, "SessionLocal", no_database)
    response = _request(client, "no-db@example.com")
    assert response.status_code == 200
    assert "database unavailable" in capsys.readouterr().err


def test_log_mode_prints_the_code_to_the_server_log(capsys):
    # client 픽스처 없이: 실제 deliver_email(log 모드)이 번호를 서버 로그(stderr)에 찍습니다.
    main.send_email_code_message("log-only@example.com", "signup", "654321")
    main.send_email_code_message("log-only@example.com", "password_reset", "765432")
    err = capsys.readouterr().err
    assert "log-only@example.com" in err
    assert "654321" in err
    assert "765432" not in err
    assert "보내지 않습니다" in err


def test_parse_email_delivery():
    for value in (None, "", "  ", "log", " LOG "):
        assert main.parse_email_delivery(value) == "log", value
    for value in ("smtp", " SMTP "):
        assert main.parse_email_delivery(value) == "smtp", value
    for value in ("resend", "smtps", "logs", "off"):
        with pytest.raises(ValueError):
            main.parse_email_delivery(value)


def test_parse_email_daily_max():
    assert main.parse_email_daily_max(None) is None
    assert main.parse_email_daily_max(" ") is None
    assert main.parse_email_daily_max("100") == 100
    for value in ("0", "-1", "1.5", "abc", "١٠"):
        with pytest.raises(ValueError):
            main.parse_email_daily_max(value)


def _import_main_with(**env):
    # 설정은 import 때 읽으므로 환경변수를 바꾼 별도 프로세스에서 봅니다.
    return run_python("import main", **env)


def test_unknown_email_settings_stop_startup():
    delivery = _import_main_with(K_DPP_EMAIL_DELIVERY="sendgird")
    assert delivery.returncode != 0
    assert "K_DPP_EMAIL_DELIVERY" in delivery.stderr
    daily_max = _import_main_with(K_DPP_EMAIL_DAILY_MAX="lots")
    assert daily_max.returncode != 0
    assert "K_DPP_EMAIL_DAILY_MAX" in daily_max.stderr
    assert _import_main_with(K_DPP_EMAIL_DELIVERY="log", K_DPP_EMAIL_DAILY_MAX="50").returncode == 0


# --- 경합·경계·이상 입력 (적대적 검토 반영) ----------------------------------------


def _pause_after_first_verify(monkeypatch):
    """처음 불리는 비밀번호 확인(해시) 직후에 멈춘다 — 확인과 쓰기 사이에 다른 요청을 끼워 넣는다."""
    reached, release = threading.Event(), threading.Event()
    original = main.verify_password
    armed = [True]

    def gated(password, stored_hash):
        ok = original(password, stored_hash)
        if armed[0]:
            armed[0] = False
            reached.set()
            release.wait(10)
        return ok

    monkeypatch.setattr(main, "verify_password", gated)
    return reached, release


def _run_paused(monkeypatch, request, while_paused):
    reached, release = _pause_after_first_verify(monkeypatch)
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("response", request()))
    worker.start()
    assert reached.wait(10)
    try:
        while_paused()
    finally:
        release.set()
        worker.join()
    return result["response"]


def _reset_now(client, email, new_password):
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")
    assert _reset(client, email, code, new_password).status_code == 200


def _token_count(email):
    session = database.SessionLocal()
    try:
        user_id = session.query(database.User.id).filter(database.User.email == email).scalar()
        return session.query(database.AccessToken).filter(
            database.AccessToken.user_id == user_id
        ).count()
    finally:
        session.close()


def test_password_change_in_flight_cannot_overwrite_a_reset(client, monkeypatch):
    # 토큰·비밀번호를 가진 사람이 비밀번호를 바꾸는 중에 주인이 비밀번호 찾기를 끝낸 경우.
    email = "takeover@example.com"
    signup(client, email)
    token = _login(client, email, "password123").json()["access_token"]

    changed = _run_paused(
        monkeypatch,
        lambda: client.post(
            "/auth/password",
            json={"current_password": "password123", "new_password": "intruder-pass"},
            headers={"Authorization": f"Bearer {token}"},
        ),
        lambda: _reset_now(client, email, "owner-pass-123"),
    )

    assert changed.status_code == 401
    assert _login(client, email, "owner-pass-123").status_code == 200
    assert _login(client, email, "intruder-pass").status_code == 401
    assert client.get("/me/history", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_login_in_flight_during_a_reset_gets_no_token(client, monkeypatch):
    email = "in-flight@example.com"
    signup(client, email)

    login = _run_paused(
        monkeypatch,
        lambda: _login(client, email, "password123"),
        lambda: _reset_now(client, email, "owner-pass-123"),
    )

    assert login.status_code == 401
    assert _token_count(email) == 0


def test_withdraw_in_flight_during_a_reset_keeps_the_account(client, monkeypatch):
    email = "withdraw-race@example.com"
    signup(client, email)
    token = _login(client, email, "password123").json()["access_token"]

    withdraw = _run_paused(
        monkeypatch,
        lambda: client.post(
            "/auth/withdraw",
            json={"password": "password123"},
            headers={"Authorization": f"Bearer {token}"},
        ),
        lambda: _reset_now(client, email, "owner-pass-123"),
    )

    assert withdraw.status_code == 401
    assert _login(client, email, "owner-pass-123").status_code == 200


def test_password_change_and_reset_lock_in_the_same_order(client, monkeypatch):
    # 변경이 users 행을 잡고 토큰을 지우는 사이에 재설정이 들어와도 교착(500) 없이 차례로 끝납니다.
    from sqlalchemy import event

    server = TestClient(main.app, raise_server_exceptions=False)
    email = "lock-order@example.com"
    signup(server, email)
    token = _login(server, email, "password123").json()["access_token"]
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    code = request_code(server, email, "password_reset")
    reached, release, armed = threading.Event(), threading.Event(), [True]

    def pause_on_token_delete(conn, cursor, statement, parameters, context, executemany):
        if armed[0] and statement.startswith("DELETE FROM access_tokens"):
            armed[0] = False
            reached.set()
            release.wait(10)

    event.listen(database.engine, "after_cursor_execute", pause_on_token_delete)
    out = {}
    try:
        change = threading.Thread(
            target=lambda: out.setdefault(
                "change",
                server.post(
                    "/auth/password",
                    json={"current_password": "password123", "new_password": "intruder-pass"},
                    headers={"Authorization": f"Bearer {token}"},
                ),
            )
        )
        change.start()
        assert reached.wait(10)
        reset = threading.Thread(
            target=lambda: out.setdefault("reset", _reset(server, email, code, "owner-pass-123"))
        )
        reset.start()
        time.sleep(0.3)
        release.set()
        change.join()
        reset.join()
    finally:
        event.remove(database.engine, "after_cursor_execute", pause_on_token_delete)

    assert out["change"].status_code == 200
    assert out["reset"].status_code == 200
    # 변경이 먼저 끝났으므로 뒤에 끝난 재설정이 이깁니다 — 변경이 받은 새 토큰도 지워집니다.
    new_token = out["change"].json()["access_token"]
    assert server.get("/me/history", headers={"Authorization": f"Bearer {new_token}"}).status_code == 401
    assert _login(server, email, "owner-pass-123").status_code == 200


def test_one_reset_code_cannot_be_used_twice_at_once(client):
    email = "double-reset@example.com"
    signup(client, email)
    with main._email_code_lock:
        main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    code = request_code(client, email, "password_reset")
    results = {}

    def reset(new_password):
        results[new_password] = _reset(client, email, code, new_password)

    threads = [
        threading.Thread(target=reset, args=(password,))
        for password in ("password-AAAA", "password-BBBB")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    codes = sorted(r.json().get("error_code", "OK") for r in results.values())
    assert codes == ["OK", "VERIFICATION_CODE_RESEND_REQUIRED"]


class _Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


def test_hourly_limit_survives_the_end_of_the_24_hour_window(client, monkeypatch):
    from datetime import datetime

    clock = _Clock(datetime(2026, 10, 5, 0, 0, 0))
    monkeypatch.setattr(main, "utc_now", clock)
    email = "day-edge@example.com"
    assert _request(client, email).status_code == 200  # 24시간 창 시작

    clock.now = datetime(2026, 10, 5, 23, 30, 0)  # 새 1시간 창에서 5번
    for _ in range(5):
        assert _request(client, email).status_code == 200
        clock.now += timedelta(seconds=61)

    # 24시간 창은 끝났지만 23:30 에 시작한 1시간 창은 아직 — 정리가 그 창을 지우면 안 됩니다.
    clock.now = datetime(2026, 10, 6, 0, 0, 1)
    blocked = _request(client, email)
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_ATTEMPTS"


def _raw_post(client, path, body):
    # 짝 없는 서로게이트(\\ud800)·제어 문자는 JSON 이스케이프로만 보낼 수 있습니다.
    return client.post(path, content=body.encode("ascii"), headers={"Content-Type": "application/json"})


def test_unprintable_emails_are_format_errors_and_count_nothing(client):
    # 짝 없는 서로게이트는 길이 상한(StringConstraints)이 붙은 칸이라 Pydantic 이 핸들러 전에
    # 422 로 거부하고, 제어 문자는 형식 검사가 400 으로 거부합니다. 둘 다 아무것도 세지 않습니다.
    for raw_email, status, error_code in (
        ("a\\ud800b@example.com", 422, "VALIDATION_ERROR"),
        ("a\\u0000b@example.com", 400, "BAD_REQUEST"),
        ("a\\u001b[31mb@example.com", 400, "BAD_REQUEST"),
    ):
        response = _raw_post(
            client, "/auth/email-code", f'{{"email":"{raw_email}","purpose":"signup"}}'
        )
        assert response.status_code == status, raw_email
        assert response.json()["error_code"] == error_code
    assert main._email_code_senders == {}
    assert main._email_code_ip_requests == {}
    assert main._email_daily_requests == {}


def test_unprintable_nickname_or_password_is_400_not_500(client):
    server = TestClient(main.app, raise_server_exceptions=False)
    code = request_code(server, "odd-input@example.com")

    nul_nickname = _raw_post(
        server,
        "/auth/signup",
        '{"email":"odd-input@example.com","password":"password123","nickname":"ab\\u0000cd",'
        f'"code":"{code}"}}',
    )
    assert nul_nickname.status_code == 400
    surrogate_password = _raw_post(
        server,
        "/auth/signup",
        '{"email":"odd-input@example.com","password":"pass\\udc80word1","nickname":"abcd",'
        f'"code":"{code}"}}',
    )
    # 길이 상한(StringConstraints)이 붙은 칸은 짝 없는 서로게이트를 Pydantic 이 핸들러 전에
    # 422 string_unicode 로 거부합니다 — 500 이 아니고 아무것도 세지 않는 것은 같습니다.
    assert surrogate_password.status_code == 422
    assert surrogate_password.json()["error_code"] == "VALIDATION_ERROR"
    # 형식 오류는 번호를 쓰지 않으므로 같은 번호로 가입할 수 있습니다.
    assert signup(server, "odd-input@example.com", code=code).status_code == 200

    with main._email_code_lock:
        main._email_code_senders["odd-input@example.com"].last_requested_at -= timedelta(minutes=1)
    reset_code = request_code(server, "odd-input@example.com", "password_reset")
    surrogate_reset = _raw_post(
        server,
        "/auth/password-reset",
        '{"email":"odd-input@example.com","new_password":"new\\udc80password",'
        f'"code":"{reset_code}"}}',
    )
    assert surrogate_reset.status_code == 422
    assert surrogate_reset.json()["error_code"] == "VALIDATION_ERROR"
    surrogate_login = _raw_post(
        server, "/auth/login", '{"email":"odd-input@example.com","password":"pass\\udc80word1"}'
    )
    assert surrogate_login.status_code == 422
    assert surrogate_login.json()["error_code"] == "VALIDATION_ERROR"


def test_resend_after_waits_for_the_limit_this_request_reached(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_IP_HOURLY_MAX", 2)
    assert _request(client, "first@example.com").json()["resend_after"] == 60
    # 이 요청으로 IP 한도(2)에 닿았으므로 60초 뒤가 아니라 그 창이 풀릴 때 다시 받을 수 있습니다.
    reached_ip = _request(client, "second@example.com").json()["resend_after"]
    assert 3500 < reached_ip <= 3600

    monkeypatch.setattr(main, "EMAIL_CODE_IP_HOURLY_MAX", 100)
    email = "fifth@example.com"
    for _ in range(4):
        assert _request(client, email).json()["resend_after"] == 60
        with main._email_code_lock:
            main._email_code_senders[email].last_requested_at -= timedelta(minutes=1)
    fifth = _request(client, email).json()["resend_after"]
    assert 3500 < fifth <= 3600
    assert _request(client, email).status_code == 429


def test_sender_records_are_capped_without_evicting_anyone(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_CODE_RECORDS_MAX_ENTRIES", 2)
    assert _request(client, "kept-1@example.com").status_code == 200
    assert _request(client, "kept-2@example.com").status_code == 200

    full = _request(client, "new-3@example.com")
    assert full.status_code == 503
    assert full.json()["error_code"] == "EMAIL_SEND_UNAVAILABLE"
    # 이미 기록이 있는 이메일은 그대로 받습니다(지우지 않으므로 그 한도도 그대로).
    with main._email_code_lock:
        main._email_code_senders["kept-1@example.com"].last_requested_at -= timedelta(minutes=1)
    assert _request(client, "kept-1@example.com").status_code == 200
    assert set(main._email_code_senders) == {"kept-1@example.com", "kept-2@example.com"}
