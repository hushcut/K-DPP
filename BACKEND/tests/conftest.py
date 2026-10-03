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
PER_TEST_TABLES = ("analysis_results", "access_tokens", "users")


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
def client():
    with database.engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(PER_TEST_TABLES)} RESTART IDENTITY")
        )
    # 로그인 잠금 카운터는 프로세스 메모리에 남으므로 테스트마다 초기화합니다.
    main._login_failures.clear()

    with TestClient(main.app) as test_client:
        yield test_client
