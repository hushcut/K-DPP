import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB_PATH = Path(__file__).resolve().parents[1] / ".pytest_k_dpp.db"
os.environ["K_DPP_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

import database  # noqa: E402
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
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink(missing_ok=True)
