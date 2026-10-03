import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


# 테스트는 로컬 PostgreSQL(BACKEND/compose.yaml)의 테스트 전용 DB 를 씁니다.
# 테스트마다 표를 모두 지우고 다시 만들므로, 실수로 실제 DB 를 가리키지 않도록
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

try:
    import database  # noqa: E402
except OperationalError as error:
    pytest.exit(
        "테스트용 PostgreSQL 에 연결하지 못했습니다. BACKEND 에서 "
        "`docker compose up -d --wait` 로 띄웠는지 확인하세요.\n"
        f"{error.orig}",
        returncode=4,
    )
import init_data  # noqa: E402
import main  # noqa: E402


@pytest.fixture()
def client():
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    init_data.seed_materials()
    # 로그인 잠금 카운터는 프로세스 메모리에 남으므로 테스트마다 초기화합니다.
    main._login_failures.clear()

    with TestClient(main.app) as test_client:
        yield test_client

    database.Base.metadata.drop_all(bind=database.engine)
    database.engine.dispose()
