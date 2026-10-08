"""SMTP 발송(DECISIONS 171) 테스트.

3.12 엔 smtpd 가 없어 이 파일 안에 작은 SMTP 서버를 둡니다. 자체 인증서(cryptography — google-auth 의
의존성으로 이미 고정됨)로 진짜 STARTTLS·처음부터 TLS 를 하므로, 실제 smtplib 이 서버 인증서·호스트
이름을 확인하고 TLS 안에서만 로그인하는지까지 봅니다. 서버는 127.0.0.1 에서만 받습니다.
"""

import base64
import socket
import ssl
import threading
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.policy import default as email_policy

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import auth_helpers
import main
from process_helpers import run_python

# conftest 의 client 픽스처가 deliver_email 을 기록 함수로 바꾸기 전의 진짜 함수.
REAL_DELIVER_EMAIL = main.deliver_email
SENDER = "K-DPP 알림 <no-reply@send.example.com>"
PASSWORD = "re_test_Password_123"


@pytest.fixture(scope="session")
def certificate(tmp_path_factory):
    """localhost 용 자체 서명 인증서와, 그 인증서만 믿는 클라이언트 TLS 설정."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    folder = tmp_path_factory.mktemp("smtp-cert")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    (folder / "cert.pem").write_bytes(cert_pem)
    (folder / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(folder / "cert.pem", folder / "key.pem")
    client_context = ssl.create_default_context(cadata=cert_pem.decode("ascii"))
    return server_context, client_context


class _Session:
    def __init__(self):
        self.lines = []  # (TLS 안이었는지, 받은 줄 그대로)
        self.commands = []
        self.auth = None  # (사용자, 비밀번호, TLS 안이었는지)
        self.mail_from = None
        self.rcpt = []
        self.data = None
        self.error = None
        # TLS 로 감싸면 원래 소켓은 떼어지므로(detach), 실제로 쓴 소켓·파일을 모아 두었다가 끝에 닫습니다.
        # 안 닫으면 예외의 traceback 이 붙잡아, 시간 상한 없는 클라이언트가 끝없이 기다립니다.
        self.closables = []


class SmtpTestServer:
    """연결마다 한 세션을 기록하는 작은 SMTP 서버. 손잡이로 실패를 흉내 냅니다."""

    def __init__(
        self,
        tls_context,
        *,
        offer_starttls=True,
        implicit_tls=False,
        greet=True,
        auth_reply="235 2.7.0 Authentication successful",
        echo_auth=False,
        rcpt_reply="250 2.1.5 Ok",
        quit_reply=True,
    ):
        self.tls_context = tls_context
        self.offer_starttls = offer_starttls
        self.implicit_tls = implicit_tls
        self.greet = greet
        self.auth_reply = auth_reply
        self.echo_auth = echo_auth
        self.rcpt_reply = rcpt_reply
        self.quit_reply = quit_reply
        self.sessions = []
        self._finished = threading.Condition()
        self._done = 0
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def close(self):
        self.listener.close()

    def wait(self, count=1, timeout=10):
        with self._finished:
            assert self._finished.wait_for(lambda: self._done >= count, timeout), "SMTP 세션이 끝나지 않음"
        return self.sessions

    def _serve(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            session = _Session()
            self.sessions.append(session)
            try:
                self._handle(conn, session)
            except Exception as exc:  # noqa: BLE001 — TLS 실패 등은 세션에 남겨 테스트가 봅니다.
                session.error = exc
            finally:
                for closable in reversed(session.closables):
                    closable.close()
                conn.close()
                with self._finished:
                    self._done += 1
                    self._finished.notify_all()

    def _handle(self, conn, session):
        conn.settimeout(10)
        sock, tls = conn, False
        if self.implicit_tls:
            sock, tls = self.tls_context.wrap_socket(conn, server_side=True), True
            session.closables.append(sock)
        reader = sock.makefile("rb")
        session.closables.append(reader)

        def reply(*lines):
            sock.sendall(b"".join(line.encode("ascii") + b"\r\n" for line in lines))

        if not self.greet:
            reader.readline()  # 클라이언트가 기다리다 끊을 때까지
            return
        reply("220 localhost ESMTP test")
        while True:
            line = reader.readline()
            if not line:
                return
            session.lines.append((tls, line))
            verb = line.split(b" ", 1)[0].strip().upper().decode("ascii", "replace")
            session.commands.append(verb)
            if verb in ("EHLO", "HELO"):
                features = ["250-localhost"]
                if self.offer_starttls and not tls:
                    features.append("250-STARTTLS")
                reply(*features, "250 AUTH PLAIN")
            elif verb == "STARTTLS":
                reply("220 2.0.0 Ready to start TLS")
                reader.close()
                sock, tls = self.tls_context.wrap_socket(sock, server_side=True), True
                reader = sock.makefile("rb")
                session.closables += [sock, reader]
            elif verb == "AUTH":
                _, user, password = base64.b64decode(line.split()[2]).split(b"\0")
                session.auth = (user.decode(), password.decode(), tls)
                if self.echo_auth:  # 받은 AUTH 줄을 거부 문구에 되돌려 주는 서버
                    reply("535 5.7.8 Authentication failed: " + line.decode().strip())
                else:
                    reply(self.auth_reply)
            elif verb == "MAIL":
                session.mail_from = line.decode().split(":", 1)[1].strip()
                reply("250 2.1.0 Ok")
            elif verb == "RCPT":
                session.rcpt.append(line.decode().split(":", 1)[1].strip())
                reply(self.rcpt_reply)
            elif verb == "DATA":
                reply("354 End data with <CR><LF>.<CR><LF>")
                chunks = []
                while (chunk := reader.readline()) not in (b".\r\n", b""):
                    chunks.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                session.data = b"".join(chunks)
                reply("250 2.0.0 Ok: queued")
            elif verb == "QUIT":
                if self.quit_reply:
                    reply("221 2.0.0 Bye")
                return
            else:
                reply("502 5.5.2 Unknown command")


@pytest.fixture()
def smtp(certificate, monkeypatch):
    """SMTP 서버를 띄우고 main 을 smtp 모드로 그 서버에 붙이는 함수를 준다."""
    server_context, client_context = certificate
    servers = []

    def start(*, host="localhost", tls_context=client_context, **knobs):
        server = SmtpTestServer(server_context, **knobs)
        servers.append(server)
        if knobs.get("implicit_tls"):
            monkeypatch.setattr(main, "SMTP_IMPLICIT_TLS_PORTS", {server.port})
        monkeypatch.setattr(main, "EMAIL_DELIVERY", "smtp")
        monkeypatch.setattr(main, "SMTP_SETTINGS", _settings(host, server.port))
        monkeypatch.setattr(main, "_EMAIL_SSL_CONTEXT", tls_context)
        return server

    yield start
    for server in servers:
        server.close()


def _settings(host, port):
    return main.SmtpSettings(
        host=host,
        port=port,
        username="resend",
        sender=SENDER,
        sender_address="no-reply@send.example.com",
        password=PASSWORD,
    )


def _signup_message(to="new@example.com", code="123456"):
    return main.compose_email_code_message(to, "signup", code, registered=False)


# --- 실제 SMTP 대화 ---------------------------------------------------------------


def test_smtp_sends_over_starttls(smtp, capsys):
    server = smtp()
    main.deliver_email(_signup_message())
    (session,) = server.wait()

    assert session.error is None
    assert session.commands == ["EHLO", "STARTTLS", "EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]
    assert session.auth == ("resend", PASSWORD, True)  # TLS 안에서만 로그인
    assert session.mail_from == "<no-reply@send.example.com>"
    assert session.rcpt == ["<new@example.com>"]
    assert all(tls for tls, _ in session.lines[2:])  # STARTTLS 뒤 모든 줄

    # 7bit 로만 나가고(한글 머리글은 RFC 2047, 본문은 base64) 받는 쪽에서 원래 글자로 돌아온다.
    assert session.data.isascii()
    assert b"Subject: [K-DPP] =?utf-8?" in session.data
    assert b"Content-Transfer-Encoding: base64" in session.data
    mail = message_from_bytes(session.data, policy=email_policy)
    assert mail["Subject"] == "[K-DPP] 가입 인증번호"
    assert mail["From"] == SENDER
    assert mail["To"] == "new@example.com"
    assert mail["Date"].endswith("+0000")
    assert mail["Message-ID"].endswith("@send.example.com>")
    assert "가입 인증번호는 123456 입니다" in mail.get_content()

    # 서버 로그엔 보냈다는 것만 — 주소·번호·비밀번호는 남기지 않는다.
    err = capsys.readouterr().err
    assert "[email] 메일을 보냈습니다(signup)." in err
    for secret in ("123456", "new@example.com", PASSWORD):
        assert secret not in err


def test_smtp_implicit_tls_port_skips_starttls(smtp):
    server = smtp(implicit_tls=True)
    main.deliver_email(_signup_message())
    (session,) = server.wait()

    assert session.error is None
    assert session.commands == ["EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]
    assert session.auth == ("resend", PASSWORD, True)
    assert all(tls for tls, _ in session.lines)


def test_smtp_without_starttls_never_sends_the_password(smtp, capsys):
    # 가운데에서 STARTTLS 를 지운 경우도 같습니다 — 로그인하지 않고 실패로 남깁니다.
    server = smtp(offer_starttls=False)
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.commands == ["EHLO"]
    assert session.auth is None
    assert not any(PASSWORD.encode() in line for _, line in session.lines)
    err = capsys.readouterr().err
    assert "인증 메일 처리 실패(signup)" in err
    assert "SMTPNotSupportedError" in err
    assert PASSWORD not in err


def test_smtp_rejects_an_untrusted_certificate(smtp, capsys):
    # 실제 설정(certifi 묶음)은 자체 서명 인증서를 믿지 않습니다 — 로그인 전에 끊깁니다.
    server = smtp(tls_context=main._EMAIL_SSL_CONTEXT)
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.commands == ["EHLO", "STARTTLS"]
    assert session.auth is None
    assert "SSLCertVerificationError" in capsys.readouterr().err


def test_smtp_implicit_tls_rejects_an_untrusted_certificate(smtp, capsys):
    # SMTP_SSL 은 context 를 주지 않으면 인증서를 확인하지 않습니다 — 465 쪽도 확인하는지.
    server = smtp(implicit_tls=True, tls_context=main._EMAIL_SSL_CONTEXT)
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.commands == []
    assert session.auth is None
    assert "SSLCertVerificationError" in capsys.readouterr().err


def test_smtp_checks_the_host_name(smtp, capsys):
    # 믿는 인증서라도 이름(localhost)이 접속한 이름(127.0.0.1)과 다르면 끊습니다.
    server = smtp(host="127.0.0.1")
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.auth is None
    err = capsys.readouterr().err
    assert "SSLCertVerificationError" in err
    assert "127.0.0.1" in err


def test_smtp_login_failure_is_logged_without_the_password(smtp, capsys):
    server = smtp(auth_reply="535 5.7.8 Authentication credentials invalid")
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.commands == ["EHLO", "STARTTLS", "EHLO", "AUTH"]
    err = capsys.readouterr().err
    assert "인증 메일 처리 실패(signup)" in err
    assert "SMTPAuthenticationError" in err
    assert PASSWORD not in err
    assert "메일을 보냈습니다" not in err
    assert err.count("\n") == 1  # 여러 줄 traceback 이 아니라 한 줄


def test_smtp_failure_log_hides_echoed_credentials(smtp, capsys):
    # 받은 AUTH 줄을 되돌려 주는 서버여도 로그엔 비밀번호도 그 base64 도 남지 않습니다.
    server = smtp(echo_auth=True)
    main.send_email_code_message("new@example.com", "signup", "123456")
    server.wait()
    err = capsys.readouterr().err
    credentials = base64.b64encode(b"\0resend\0" + PASSWORD.encode()).decode()
    assert "SMTPAuthenticationError" in err
    assert "<비밀번호>" in err
    assert credentials not in err
    assert PASSWORD not in err


def test_smtp_failure_log_hides_the_recipient(smtp, capsys):
    # 비밀번호 찾기 메일은 가입된 이메일에만 가므로 실패 줄의 주소는 가입 여부까지 남깁니다.
    server = smtp(rcpt_reply="550 5.1.1 Recipient rejected")
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()
    assert session.data is None
    err = capsys.readouterr().err
    assert "SMTPRecipientsRefused" in err
    assert "<받는 주소>" in err
    assert "new@example.com" not in err
    assert err.count("\n") == 1


def test_smtp_quit_failure_after_sending_is_not_a_failure(smtp, capsys):
    server = smtp(quit_reply=False)
    main.send_email_code_message("new@example.com", "signup", "123456")
    (session,) = server.wait()

    assert session.data is not None
    err = capsys.readouterr().err
    assert "[email] 메일을 보냈습니다(signup)." in err
    assert "실패" not in err


def test_smtp_connection_refused_is_logged(smtp, monkeypatch, capsys):
    smtp()
    with socket.create_server(("127.0.0.1", 0)) as probe:
        closed_port = probe.getsockname()[1]
    monkeypatch.setattr(main, "SMTP_SETTINGS", _settings("localhost", closed_port))
    main.send_email_code_message("new@example.com", "signup", "123456")
    err = capsys.readouterr().err
    assert "인증 메일 처리 실패(signup)" in err
    assert "ConnectionRefusedError" in err


def test_smtp_silent_server_times_out(smtp, monkeypatch, capsys):
    server = smtp(greet=False)
    monkeypatch.setattr(main, "SMTP_TIMEOUT_SECONDS", 0.5)
    main.send_email_code_message("new@example.com", "signup", "123456")
    server.wait()
    err = capsys.readouterr().err
    assert "인증 메일 처리 실패(signup)" in err
    assert "timed out" in err


def test_smtp_silent_server_times_out_on_implicit_tls(smtp, monkeypatch, capsys):
    server = smtp(implicit_tls=True, greet=False)
    monkeypatch.setattr(main, "SMTP_TIMEOUT_SECONDS", 0.5)
    main.send_email_code_message("new@example.com", "signup", "123456")
    server.wait()
    err = capsys.readouterr().err
    assert "인증 메일 처리 실패(signup)" in err
    assert "timed out" in err


def test_unregistered_password_reset_sends_and_logs_nothing(smtp, capsys):
    # smtp 모드에선 '가입되지 않은 이메일이라…' 줄(주소 포함 — 가입 여부)을 찍지 않고 연결도 하지 않습니다.
    server = smtp()
    main.send_email_code_message("nobody-smtp@example.com", "password_reset", "123456")
    assert server.sessions == []
    assert capsys.readouterr().err == ""


def test_address_smtp_reads_differently_is_not_sent(smtp, capsys):
    # 형식 검사가 막는 표기지만, 들어와도 연결하지 않고 주소 없이 실패만 남깁니다.
    server = smtp()
    for address in ('"victim@company.com"', "victim@company.com(1)", "x<victim@company.com"):
        main.send_email_code_message(address, "signup", "123456")
    assert server.sessions == []
    err = capsys.readouterr().err
    assert err.count("다른 주소로 읽어 보내지 않습니다") == 3
    assert "victim@company.com" not in err


def test_production_tls_settings():
    # 테스트는 시험 인증서를 믿는 설정으로 바꿔 끼우므로, 실제 설정의 성질은 따로 봅니다.
    context = main._EMAIL_SSL_CONTEXT
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    certifi_bundle = ssl.create_default_context(cafile=certifi.where())
    assert context.cert_store_stats() == certifi_bundle.cert_store_stats()
    assert main.SMTP_IMPLICIT_TLS_PORTS == {465, 2465}


@pytest.mark.parametrize(
    "address",
    [
        '"victim@company.com"',
        "<victim@company.com>",
        "victim@company.com(1)",
        "x<victim@company.com",
        "a:victim@company.com;",
        "victim@company.com,other@company.com",
        "victim\\@company.com",
        "사용자@example.com",
        "user@한국.kr",
    ],
)
def test_addresses_smtp_would_read_differently_are_rejected(client, address):
    # ASCII 밖 글자·주소 문법 글자가 든 이메일은 번호 요청·가입·비밀번호 찾기 모두 400(DECISIONS 175).
    requests = [
        ("/auth/email-code", {"email": address, "purpose": "signup"}),
        ("/auth/signup", {"email": address, "password": "password123", "nickname": "tester", "code": "123456"}),
        ("/auth/password-reset", {"email": address, "code": "123456", "new_password": "password456"}),
    ]
    for path, body in requests:
        response = client.post(path, json=body)
        assert response.status_code == 400, (path, response.text)
        assert response.json()["detail"] == "올바른 이메일을 입력해 주세요."
    assert auth_helpers.SENT_EMAILS == []


def test_email_code_requests_send_through_smtp(client, smtp, monkeypatch):
    # HTTP 요청 → 응답 뒤 백그라운드 → SMTP 까지 이어지는지. 메일 속 번호로 가입이 되고, 이미 가입된
    # 이메일로 다시 요청하면 번호 없는 안내 메일이 같은 길로 간다.
    monkeypatch.setattr(main, "deliver_email", REAL_DELIVER_EMAIL)
    monkeypatch.setattr(main, "EMAIL_CODE_RESEND_SECONDS", 0)
    server = smtp()

    response = client.post("/auth/email-code", json={"email": "Smtp@Example.com", "purpose": "signup"})
    assert response.status_code == 200
    (first,) = server.wait(1)
    assert first.rcpt == ["<smtp@example.com>"]
    body = message_from_bytes(first.data, policy=email_policy).get_content()
    code = body.split("인증번호는 ", 1)[1][:6]
    assert auth_helpers.signup(client, "smtp@example.com", code=code).status_code == 200

    response = client.post("/auth/email-code", json={"email": "smtp@example.com", "purpose": "signup"})
    assert response.status_code == 200
    second = server.wait(2)[1]
    notice = message_from_bytes(second.data, policy=email_policy)
    assert notice["Subject"] == "[K-DPP] 이미 가입된 이메일입니다"
    assert "인증번호는" not in notice.get_content()


# --- 설정 ---------------------------------------------------------------------------


def _env(tmp_path, **overrides):
    password_file = tmp_path / "smtp_password"
    password_file.write_text(PASSWORD + "\n", encoding="utf-8")
    env = {
        "K_DPP_SMTP_HOST": "smtp.resend.com",
        "K_DPP_SMTP_PORT": "587",
        "K_DPP_SMTP_USERNAME": "resend",
        "K_DPP_SMTP_PASSWORD_FILE": str(password_file),
        "K_DPP_EMAIL_FROM": SENDER,
        "K_DPP_EMAIL_DAILY_MAX": "100",
    }
    env.update(overrides)
    return env


def test_parse_smtp_settings_reads_everything(tmp_path):
    settings = main.parse_smtp_settings("smtp", _env(tmp_path, K_DPP_SMTP_HOST=" smtp.resend.com "))
    assert settings == main.SmtpSettings(
        host="smtp.resend.com",
        port=587,
        username="resend",
        sender=SENDER,
        sender_address="no-reply@send.example.com",
        password=PASSWORD,
    )
    # 설정을 로그나 예외로 찍어도 비밀번호는 보이지 않습니다.
    assert PASSWORD not in repr(settings)


def test_log_mode_reads_no_smtp_setting():
    assert main.parse_smtp_settings("log", {"K_DPP_SMTP_PASSWORD_FILE": "/없는/파일"}) is None


def test_parse_smtp_settings_requires_every_setting(tmp_path):
    for name in main.SMTP_REQUIRED_SETTINGS:
        for empty in ("", "  "):
            with pytest.raises(ValueError, match=name):
                main.parse_smtp_settings("smtp", _env(tmp_path, **{name: empty}))
        env = _env(tmp_path)
        del env[name]
        with pytest.raises(ValueError, match=name):
            main.parse_smtp_settings("smtp", env)


@pytest.mark.parametrize(
    "name, value",
    [
        ("K_DPP_SMTP_HOST", "smtp resend.com"),
        ("K_DPP_SMTP_HOST", "smtp.resend.com:587"),
        ("K_DPP_SMTP_PORT", "0"),
        ("K_DPP_SMTP_PORT", "65536"),
        ("K_DPP_SMTP_PORT", "587a"),
        ("K_DPP_SMTP_PORT", "５８７"),
        ("K_DPP_SMTP_USERNAME", "레센드"),
        ("K_DPP_EMAIL_FROM", "K-DPP"),
        ("K_DPP_EMAIL_FROM", "<>"),
        ("K_DPP_EMAIL_FROM", "a@b.com, c@d.com"),
        ("K_DPP_EMAIL_FROM", "K-DPP <no-reply@send.example.com"),
        ("K_DPP_EMAIL_FROM", "K-DPP <no-reply@send.example.com> junk"),
        ("K_DPP_EMAIL_FROM", "no-reply@localhost"),
        ("K_DPP_EMAIL_FROM", "알림@send.example.com"),
        ("K_DPP_EMAIL_FROM", "a@b.com\r\nBcc: x@y.com"),
        # 헤더 파서는 결함으로 보지 않지만 막는 것: 한글 도메인(받는 쪽 SMTPUTF8 필요)·줄 구분 문자.
        ("K_DPP_EMAIL_FROM", "no-reply@send.한국"),
        ("K_DPP_EMAIL_FROM", "K\u2028DPP <no-reply@send.example.com>"),
        ("K_DPP_EMAIL_FROM", "G: no-reply@send.example.com;"),
    ],
)
def test_parse_smtp_settings_rejects_bad_values(tmp_path, name, value):
    with pytest.raises(ValueError, match=name):
        main.parse_smtp_settings("smtp", _env(tmp_path, **{name: value}))


def test_email_from_accepts_plain_and_named_addresses(tmp_path):
    for sender in ("no-reply@send.example.com", '"K-DPP" <no-reply@send.example.com>', SENDER):
        settings = main.parse_smtp_settings("smtp", _env(tmp_path, K_DPP_EMAIL_FROM=sender))
        assert settings.sender_address == "no-reply@send.example.com"


@pytest.mark.parametrize(
    "content",
    [b"", b" \n", PASSWORD.encode() + b"\nsecond-line", "비밀번호".encode(), b"\xff\xfe"],
)
def test_smtp_password_file_must_be_one_ascii_line(tmp_path, content):
    path = tmp_path / "bad_password"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="K_DPP_SMTP_PASSWORD_FILE") as error:
        main.parse_smtp_settings("smtp", _env(tmp_path, K_DPP_SMTP_PASSWORD_FILE=str(path)))
    assert PASSWORD not in str(error.value)
    assert "비밀번호" not in str(error.value)


def test_smtp_password_file_must_be_readable(tmp_path):
    for path in (tmp_path / "missing", tmp_path):  # 없는 파일·폴더
        with pytest.raises(ValueError, match="K_DPP_SMTP_PASSWORD_FILE"):
            main.parse_smtp_settings("smtp", _env(tmp_path, K_DPP_SMTP_PASSWORD_FILE=str(path)))


def _import_main_with(**env):
    # 설정은 import 때 읽으므로 환경변수를 바꾼 별도 프로세스에서 봅니다.
    return run_python("import main", **env)


def test_smtp_settings_decide_whether_the_server_starts(tmp_path):
    nothing = _import_main_with(K_DPP_EMAIL_DELIVERY="smtp")
    assert nothing.returncode != 0
    assert "K_DPP_SMTP_HOST" in nothing.stderr
    assert "K_DPP_EMAIL_DAILY_MAX" in nothing.stderr

    bad_sender = _import_main_with(K_DPP_EMAIL_DELIVERY="smtp", **_env(tmp_path, K_DPP_EMAIL_FROM="K-DPP"))
    assert bad_sender.returncode != 0
    assert "K_DPP_EMAIL_FROM" in bad_sender.stderr
    assert PASSWORD not in bad_sender.stderr + bad_sender.stdout

    # 값은 문구에 넣지 않습니다 — API 키를 엉뚱한 칸에 넣어도 시작 로그에 남지 않게.
    key = "re_FAKEKEY_abc123"
    for name in ("K_DPP_SMTP_HOST", "K_DPP_SMTP_USERNAME", "K_DPP_SMTP_PASSWORD_FILE", "K_DPP_EMAIL_FROM"):
        misplaced = _import_main_with(K_DPP_EMAIL_DELIVERY="smtp", **_env(tmp_path, **{name: key + "\tx"}))
        assert misplaced.returncode != 0, name
        assert name in misplaced.stderr
        assert key not in misplaced.stderr + misplaced.stdout, name

    assert _import_main_with(K_DPP_EMAIL_DELIVERY="smtp", **_env(tmp_path)).returncode == 0
