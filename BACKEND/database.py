from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. DB 파일 경로 설정
# 서버를 어느 폴더에서 실행하더라도 BACKEND/k_dpp.db를 사용합니다.
DB_PATH = Path(__file__).resolve().parent / "k_dpp.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# 2. 엔진 및 세션 설정
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 3. 소재별 평균 탄소배출량 표준 테이블

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    nickname = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


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
    materials = Column(Text, nullable=False)
    carbon_footprint = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="kg CO2eq")
    raw_ocr_text = Column(Text)
    unknown_materials = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


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


# 5. 서버 실행 시 필요한 테이블과 컬럼을 준비합니다.
ensure_schema()
