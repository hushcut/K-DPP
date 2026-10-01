"""분석 결과마다 어떤 계수표로 계산했는지 남기는지 확인한다.

`analysis_results` 는 결과마다 반올림 전 혼합 계수(`carbon_factor`)와 계수표 버전
(`factor_version` = `init_data.FACTOR_VERSION`)을 저장한다. 계수표를 바꾼 뒤에도 옛 기록을
구분하기 위해서다. 버전 기록 전에 저장된 행은 두 칸이 NULL 이다.

버전이 계수표를 정말 가리키려면, 계수만 바꾸고 버전을 그대로 두는 커밋이 막혀야 한다.
그래서 버전마다 계수표 지문을 아래 표에 고정해 둔다.
"""

import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import database
import init_data


# 계수표를 바꾸면 FACTOR_VERSION 을 올리고, 새 버전과 (테스트 실패 메시지에 찍히는) 새 지문을
# 여기에 한 줄 더한다. 옛 줄은 지우지 않는다 — 옛 버전 이름을 다른 계수표에 다시 쓰는 것도 막는다.
KNOWN_FACTOR_TABLES = {
    "dev-estimate-v1": "ebc753a8a1a88dbda5bb828d50a7d5d2bf8e799d60c7e6b0bfc4734fe983976f",
}


def factor_table_fingerprint() -> str:
    # 별칭은 넣지 않는다. 입력 이름을 어느 소재에 붙일지의 규칙이지 계수가 아니다.
    table = sorted(
        (seed["name_en"], float(seed["carbon_factor"]))
        for seed in init_data.MATERIAL_SEEDS
    )
    payload = json.dumps(
        {"factors": table, "unit": init_data.TEXTILE_UNIT},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_factor_version_points_to_current_factor_table():
    version = init_data.FACTOR_VERSION
    fingerprint = factor_table_fingerprint()

    assert version in KNOWN_FACTOR_TABLES, (
        f"FACTOR_VERSION {version!r} 이 KNOWN_FACTOR_TABLES 에 없습니다. "
        f"계수표를 바꾼 것이 맞다면 {version!r}: {fingerprint!r} 를 더하세요."
    )
    assert KNOWN_FACTOR_TABLES[version] == fingerprint, (
        f"계수표가 {version!r} 때와 다릅니다. 계수표를 바꿨다면 init_data.FACTOR_VERSION 을 "
        f"새 이름으로 올리고 KNOWN_FACTOR_TABLES 에 그 이름: {fingerprint!r} 를 더하세요."
    )


def _auth_headers(client, email: str) -> dict:
    client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "nickname": email.split("@")[0]},
    )
    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_calculate_saves_unrounded_factor_and_version(client):
    headers = _auth_headers(client, "factor-version@example.com")

    # 8.3 × 0.33 + 9.5 × 0.67 = 9.104 → 계산 응답은 둘째 자리(9.1), 저장은 반올림 전 값.
    response = client.post(
        "/api/carbon/calculate",
        json={
            "materials": {"cotton": 33, "polyester": 67},
            "min_weight_grams": 100,
            "max_weight_grams": 250,
        },
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 200
    assert body["carbon_factor"] == 9.1
    assert body["factor_version"] == init_data.FACTOR_VERSION

    history = client.get("/me/history", headers=headers).json()["history"]
    assert history[0]["id"] == body["saved_result_id"]
    assert history[0]["carbon_factor"] == pytest.approx(9.104)
    assert history[0]["factor_version"] == init_data.FACTOR_VERSION


def test_history_returns_null_for_rows_saved_before_versioning(client):
    headers = _auth_headers(client, "legacy-row@example.com")
    user_id = client.get("/me/history", headers=headers).json()["user"]["id"]

    db = database.SessionLocal()
    try:
        db.add(
            database.AnalysisResult(
                user_id=user_id,
                materials=json.dumps({"cotton": 100}),
                carbon_footprint=1.46,
                carbon_footprint_min=0.83,
                carbon_footprint_max=2.08,
                min_weight_grams=100,
                max_weight_grams=250,
            )
        )
        db.commit()
    finally:
        db.close()

    history = client.get("/me/history", headers=headers).json()["history"]

    assert len(history) == 1
    assert history[0]["carbon_factor"] is None
    assert history[0]["factor_version"] is None
    assert history[0]["materials"] == {"cotton": 100}
    assert history[0]["carbon_footprint"] == 1.46
    assert history[0]["carbon_footprint_min"] == 0.83
    assert history[0]["carbon_footprint_max"] == 2.08


# 버전 칸이 생기기 전의 analysis_results. 실제 DB 는 만든 시점에 따라 둘 중 하나에서
# ensure_schema 의 ADD COLUMN 을 거쳐 왔다.
OLD_SCHEMAS = {
    # 04-14 f798954 의 첫 스키마. 이후 칸은 모두 ADD COLUMN 으로 붙는다.
    "first_schema": (
        """
        CREATE TABLE analysis_results (
            id INTEGER NOT NULL,
            materials VARCHAR,
            carbon_footprint FLOAT,
            PRIMARY KEY (id)
        )
        """,
        [
            {"id": 1, "materials": '{"cotton": 80, "polyester": 20}', "carbon_footprint": 8.54},
            {"id": 2, "materials": '{"wool": 100}', "carbon_footprint": 13.9},
        ],
    ),
    # 버전 칸 직전(develop cc5e44a)에 새로 만든 DB.
    "before_factor_version": (
        """
        CREATE TABLE analysis_results (
            id INTEGER NOT NULL,
            user_id INTEGER,
            materials TEXT NOT NULL,
            carbon_footprint FLOAT NOT NULL,
            carbon_footprint_min FLOAT,
            carbon_footprint_max FLOAT,
            min_weight_grams FLOAT,
            max_weight_grams FLOAT,
            unit VARCHAR NOT NULL,
            raw_ocr_text TEXT,
            unknown_materials TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
        """,
        [
            {
                # 무게가 있는 행(06-06 이후 /api/carbon/calculate).
                "id": 1,
                "user_id": 1,
                "materials": '{"cotton": 100}',
                "carbon_footprint": 1.46,
                "carbon_footprint_min": 0.83,
                "carbon_footprint_max": 2.08,
                "min_weight_grams": 100.0,
                "max_weight_grams": 250.0,
                "unit": "kg CO2eq",
                "raw_ocr_text": "COTTON 100%",
                "unknown_materials": "[]",
                "created_at": "2026-09-26 06:03:00.000000",
            },
            {
                # 무게가 없는 행(옛 /analyze 저장).
                "id": 2,
                "user_id": 1,
                "materials": '{"cotton": 80, "polyester": 20}',
                "carbon_footprint": 8.54,
                "carbon_footprint_min": None,
                "carbon_footprint_max": None,
                "min_weight_grams": None,
                "max_weight_grams": None,
                "unit": "kg CO2eq",
                "raw_ocr_text": None,
                "unknown_materials": "[]",
                "created_at": "2026-05-20 10:00:00.000000",
            },
        ],
    ),
}


@pytest.mark.parametrize("schema_name", OLD_SCHEMAS)
def test_ensure_schema_adds_empty_factor_columns_to_old_db(schema_name, tmp_path, monkeypatch):
    create_sql, rows = OLD_SCHEMAS[schema_name]
    old_columns = list(rows[0])
    column_list = ", ".join(old_columns)
    select_old = f"SELECT {column_list} FROM analysis_results ORDER BY id"

    old_engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    try:
        with old_engine.begin() as connection:
            connection.exec_driver_sql(create_sql)
            placeholders = ", ".join("?" for _ in old_columns)
            connection.exec_driver_sql(
                f"INSERT INTO analysis_results ({column_list}) VALUES ({placeholders})",
                [tuple(row[column] for column in old_columns) for row in rows],
            )
            before = connection.exec_driver_sql(select_old).fetchall()

        # ensure_schema 는 모듈의 engine 을 쓰므로 옛 DB 엔진으로 바꿔 돌린다.
        monkeypatch.setattr(database, "engine", old_engine)
        database.ensure_schema()
        # 서버가 다시 켜질 때마다 돈다 — 두 번째에도 오류 없이 그대로여야 한다.
        database.ensure_schema()

        with old_engine.connect() as connection:
            columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(analysis_results)"
                ).fetchall()
            }
            after = connection.exec_driver_sql(select_old).fetchall()
            new_values = connection.exec_driver_sql(
                "SELECT carbon_factor, factor_version FROM analysis_results ORDER BY id"
            ).fetchall()

        for name in ("carbon_factor", "factor_version"):
            assert name in columns
            # PRAGMA table_info 행: (cid, name, type, notnull, dflt_value, pk)
            assert columns[name][3] == 0
            assert columns[name][4] is None

        assert after == before
        assert new_values == [(None, None)] * len(rows)

        # 이전된 DB 에서도 새 결과는 두 칸을 쓴다.
        with Session(bind=old_engine) as session:
            result = database.AnalysisResult(
                materials='{"cotton": 33, "polyester": 67}',
                carbon_footprint=1.59,
                carbon_factor=9.104,
                factor_version=init_data.FACTOR_VERSION,
            )
            session.add(result)
            session.commit()
            saved = session.get(database.AnalysisResult, result.id)
            assert saved.carbon_factor == pytest.approx(9.104)
            assert saved.factor_version == init_data.FACTOR_VERSION
    finally:
        old_engine.dispose()
