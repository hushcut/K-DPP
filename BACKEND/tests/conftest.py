import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


# 테스트는 로컬 PostgreSQL(BACKEND/compose.yaml)의 테스트 전용 DB 를 씁니다.
# 표를 모두 지우고 다시 만드므로, 실수로 실제 DB 를 가리키지 않도록
# DB 이름이 _test 로 끝나지 않으면 시작하지 않습니다.
TEST_DATABASE_URL = os.getenv(
    "K_DPP_TEST_DATABASE_URL",
    "postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp_test",
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    pytest.exit(
        "K_DPP_TEST_DATABASE_URL 의 DB 이름이 _test 로 끝나야 합니다"
        "(테스트가 표를 모두 지웁니다).",
        returncode=4,
    )
os.environ["K_DPP_DATABASE_URL"] = TEST_DATABASE_URL
# CORS 는 기본값(허용 출처 없음)으로 시험합니다. BACKEND/.env 는 이미 있는 값을 덮지 않습니다.
os.environ["K_DPP_CORS_ORIGINS"] = ""
# API 문서도 기본값(켬)으로 시험합니다. 끈 경우는 별도 프로세스로 봅니다(test_hardening).
os.environ["K_DPP_API_DOCS"] = ""
# 서버 전체 하루 스캔 상한도 기본값(없음)으로 시험합니다. 상한은 테스트가 main 값을 바꿔 봅니다.
os.environ["K_DPP_SCAN_DAILY_MAX"] = ""
# 인증 메일도 기본값(log 모드·하루 상한 없음)으로 시험합니다. 다른 값은 별도 프로세스로 봅니다.
os.environ["K_DPP_EMAIL_DELIVERY"] = ""
os.environ["K_DPP_EMAIL_DAILY_MAX"] = ""
# 카카오 로그인도 기본값(앱 ID 없음 — 꺼짐, 503)으로 시험합니다. 켠 경우는 테스트가 main.KAKAO_APP_ID 를 바꿉니다.
os.environ["K_DPP_KAKAO_APP_ID"] = ""

import auth_helpers  # noqa: E402
import database  # noqa: E402

try:
    with database.engine.connect():
        pass
except OperationalError as error:
    pytest.exit(
        "테스트용 PostgreSQL 에 연결하지 못했습니다. BACKEND 에서 "
        "`docker compose up -d --wait` 로 띄웠는지 확인하세요.\n"
        f"{error.orig}",
        returncode=4,
    )
import main  # noqa: E402

# 테스트마다 비우는 표. 소재(materials)는 마이그레이션이 넣은 값을 그대로 쓴다
# — 소재를 바꾸는 API·테스트가 없다.
PER_TEST_TABLES = ("analysis_results", "access_tokens", "social_accounts", "users")


def make_alembic_config() -> Config:
    config = Config(str(database.BACKEND_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    return config


def drop_everything() -> None:
    database.Base.metadata.drop_all(bind=database.engine)
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def migrate_fresh() -> None:
    """빈 DB 에서 `alembic upgrade head` — 배포 서버와 같은 길로 표·소재를 만든다."""
    drop_everything()
    command.upgrade(make_alembic_config(), "head")


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    migrate_fresh()
    yield
    drop_everything()
    database.engine.dispose()


@pytest.fixture()
def alembic_config():
    """마이그레이션 테스트용: DB 를 비우고 Alembic 설정을 준다. 끝나면 head 로 되돌려
    다른 테스트가 그대로 쓰게 한다."""
    drop_everything()
    yield make_alembic_config()
    migrate_fresh()


@pytest.fixture()
def client(monkeypatch):
    with database.engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(PER_TEST_TABLES)} RESTART IDENTITY")
        )
    # 로그인 잠금·가입 IP 카운터·인증번호 기록·하루 스캔 카운터는 프로세스 메모리에 남으므로 테스트마다 초기화합니다.
    main._login_failures.clear()
    main._login_ip_failures.clear()
    main._signup_ip_attempts.clear()
    main._vision_scan_counts.clear()
    main._email_codes.clear()
    main._email_code_senders.clear()
    main._email_code_ip_requests.clear()
    main._email_daily_requests.clear()
    # 인증 메일은 로그 대신 auth_helpers.SENT_EMAILS 에 모아, 가입 헬퍼가 번호를 꺼내 씁니다.
    auth_helpers.SENT_EMAILS.clear()
    monkeypatch.setattr(main, "deliver_email", auth_helpers.record_email)

    with TestClient(main.app) as test_client:
        yield test_client
