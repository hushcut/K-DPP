from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. DB 주소 설정
# 환경변수 K_DPP_DATABASE_URL → BACKEND/.env 순서로 읽고, 없으면 로컬 개발용
# PostgreSQL(BACKEND/compose.yaml)에 붙습니다. SQLite 는 더 지원하지 않습니다.
# 표는 서버가 만들지 않고 `alembic upgrade head` 로 만듭니다(migrations/).
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
SQLALCHEMY_DATABASE_URL = os.getenv(
    "K_DPP_DATABASE_URL",
    "postgresql+psycopg://kdpp:kdpp@127.0.0.1:5432/k_dpp",
)

# 2. 엔진 및 세션 설정
# pool_pre_ping: DB 가 재시작되면 풀에 남은 연결이 끊겨 있는데, 쓰기 전에 확인해
# 끊긴 연결을 버리고 새로 맺습니다(없으면 재시작 직후 끊긴 연결을 받은 요청이 500).
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 제약 이름을 규칙대로 붙입니다. Alembic 마이그레이션이 나중에 제약을 지우거나
# 바꿀 때 DB 마다 다른 자동 이름 대신 이 이름으로 가리킵니다.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


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


# 5. 서버 시작 때 스키마 확인
# 서버는 표를 만들거나 바꾸지 않습니다. 마이그레이션을 빼먹고 켜면 요청마다 500 이
# 나는 대신, 시작할 때 바로 멈추고 할 일을 알려 줍니다(main.py lifespan).
def assert_schema_current() -> None:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    head = script.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()

    if current != head:
        raise RuntimeError(
            f"DB 스키마가 최신이 아닙니다(현재 {current}, 최신 {head}). "
            "BACKEND 에서 `alembic upgrade head` 를 먼저 실행하세요."
        )
