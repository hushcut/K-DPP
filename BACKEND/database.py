from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. DB 파일 경로 설정
# 서버를 어느 폴더에서 실행하더라도 BACKEND/k_dpp.db를 사용합니다.
DB_PATH = Path(__file__).resolve().parent / "k_dpp.db"
load_dotenv(DB_PATH.parent / ".env")
SQLALCHEMY_DATABASE_URL = os.getenv(
    "K_DPP_DATABASE_URL",
    f"sqlite:///{DB_PATH.as_posix()}",
)

# 2. 엔진 및 세션 설정
# timeout: 다른 요청이 잠금을 잡고 있을 때 바로 실패하지 않고 잠시 대기합니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 5},
)

# SQLite에서 동시 요청(로그인·계산·이력 저장이 겹치는 상황)에 대비해
# WAL 모드를 켭니다. 읽기와 쓰기가 서로를 덜 막아 'database is locked'
# 오류 가능성이 크게 줄어듭니다.
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

# 3. 소재별 평균 탄소배출량 표준 테이블

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    nickname = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class AccessToken(Base):
    __tablename__ = "access_tokens"

    token = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=True)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name_ko = Column(String, unique=True, nullable=False, index=True)
    name_en = Column(String, unique=True, nullable=False, index=True)
    aliases = Column(Text, nullable=False, default="[]")
    carbon_factor = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="kg CO2eq/kg textile")

# 4. 라벨 분석 및 탄소배출량 계산 결과 저장 테이블
class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    materials = Column(Text, nullable=False)
    carbon_footprint = Column(Float, nullable=False)
    carbon_footprint_min = Column(Float, nullable=True)
    carbon_footprint_max = Column(Float, nullable=True)
    min_weight_grams = Column(Float, nullable=True)
    max_weight_grams = Column(Float, nullable=True)
    unit = Column(String, nullable=False, default="kg CO2eq")
    raw_ocr_text = Column(Text)
    unknown_materials = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=utc_now)


def ensure_schema():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        material_rows = connection.exec_driver_sql("PRAGMA table_info(materials)").fetchall()
        material_columns = {row[1] for row in material_rows}

        # 이전 개발 중 만들어진 불필요한 컬럼이 있으면 v1 스키마로 정리합니다.
        if {"source", "description"} & material_columns:
            connection.exec_driver_sql("ALTER TABLE materials RENAME TO materials_old")
            connection.exec_driver_sql(
                """
                CREATE TABLE materials_new (
                    id INTEGER NOT NULL,
                    name_ko VARCHAR NOT NULL,
                    name_en VARCHAR NOT NULL,
                    aliases TEXT NOT NULL,
                    carbon_factor FLOAT NOT NULL,
                    unit VARCHAR NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (name_ko),
                    UNIQUE (name_en)
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO materials_new (id, name_ko, name_en, aliases, carbon_factor, unit)
                SELECT id, name_ko, name_en, aliases, carbon_factor, unit
                FROM materials_old
                """
            )
            connection.exec_driver_sql("DROP TABLE materials_old")
            connection.exec_driver_sql("ALTER TABLE materials_new RENAME TO materials")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_materials_id ON materials (id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_materials_name_ko ON materials (name_ko)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_materials_name_en ON materials (name_en)"
            )

        # 기존 로컬 DB가 있어도 새 컬럼을 안전하게 추가합니다.
        rows = connection.exec_driver_sql("PRAGMA table_info(analysis_results)").fetchall()
        existing_columns = {row[1] for row in rows}

        missing_columns = {
            "user_id": "INTEGER",
            "carbon_footprint_min": "FLOAT",
            "carbon_footprint_max": "FLOAT",
            "min_weight_grams": "FLOAT",
            "max_weight_grams": "FLOAT",
            "unit": "VARCHAR DEFAULT 'kg CO2eq' NOT NULL",
            "raw_ocr_text": "TEXT",
            "unknown_materials": "TEXT DEFAULT '[]' NOT NULL",
            "created_at": "DATETIME",
        }

        for column_name, column_sql in missing_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE analysis_results ADD COLUMN {column_name} {column_sql}"
                )

        token_rows = connection.exec_driver_sql(
            "PRAGMA table_info(access_tokens)"
        ).fetchall()
        token_columns = {row[1] for row in token_rows}
        if "expires_at" not in token_columns:
            connection.exec_driver_sql(
                "ALTER TABLE access_tokens ADD COLUMN expires_at DATETIME"
            )


# 5. 서버 실행 시 필요한 테이블과 컬럼을 준비합니다.
ensure_schema()
