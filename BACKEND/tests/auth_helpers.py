"""가입·인증번호 테스트 헬퍼.

가입에 이메일 인증번호가 필요해(DECISIONS 147) 가입하는 테스트는 모두 이 헬퍼를 거칩니다.
conftest 의 client 픽스처가 main.deliver_email 을 record_email 로 바꿔, 메일 대신 SENT_EMAILS 에
쌓인 번호를 꺼내 씁니다.
"""

SENT_EMAILS = []


def record_email(message):
    SENT_EMAILS.append(message)


def latest_email(email, purpose):
    email = email.strip().lower()
    for message in reversed(SENT_EMAILS):
        if message.to == email and message.purpose == purpose:
            return message
    return None


def request_code(client, email, purpose="signup"):
    """번호를 요청하고 그 메일의 번호를 돌려준다(번호 없는 안내 메일·메일 없음이면 None)."""
    response = client.post("/auth/email-code", json={"email": email, "purpose": purpose})
    assert response.status_code == 200, response.text
    message = latest_email(email, purpose)
    return message.code if message is not None else None


def signup(client, email, password="password123", nickname="tester", code=None):
    """번호를 받아 가입한다. code 를 주면 번호 요청 없이 그 번호로 가입만 한다."""
    if code is None:
        code = request_code(client, email)
        assert code is not None, f"{email} 로 가입 인증번호가 오지 않았습니다(이미 가입됨?)"
    return client.post(
        "/auth/signup",
        json={"email": email, "password": password, "nickname": nickname, "code": code},
    )


def fix_next_code(monkeypatch, code="123456"):
    """다음에 만들 번호를 고정한다 — 메일이 가지 않는 경우(이미 가입·가입 안 된 재설정)를 시험할 때."""
    import main

    monkeypatch.setattr(main, "generate_email_code", lambda: code)
    return code
