import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


# 테스트는 로컬 PostgreSQL 의 테스트 전용 DB 를 씁니다. 표를 모두 지우고 다시
# 만드므로, 실수로 실제 DB 를 가리키지 않도록 DB 이름이 _test 로 끝나지 않으면
# 시작하지 않습니다. develop 의 테스트 DB(k_dpp_test, K_DPP_TEST_DATABASE_URL)와
# 섞이면 v2 표·트리거 함수가 남아 그쪽 테스트가 깨지므로 변수와 DB 를 따로 씁니다.
TEST_DATABASE_URL = os.getenv(
    "K_DPP_V2_TEST_DATABASE_URL",
    "postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp_v2_test",
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    pytest.exit(
        "K_DPP_V2_TEST_DATABASE_URL 의 DB 이름이 _test 로 끝나야 합니다"
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
        "테스트용 PostgreSQL 에 연결하지 못했습니다. 컨테이너가 떠 있는지와 "
        "k_dpp_v2_test DB 가 있는지 확인하세요(README '테스트').\n"
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

    with TestClient(main.app) as test_client:
        yield test_client

    database.Base.metadata.drop_all(bind=database.engine)
    database.engine.dispose()
