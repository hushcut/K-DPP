from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, CheckConstraint, Index, create_engine, event
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
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        """Make declared relationships enforceable on every SQLite connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
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
class MaterialFactor(Base):
    __tablename__ = "material_factors"
    __table_args__ = (
        UniqueConstraint("factor_key", "version"),
        CheckConstraint("review_status IN ('candidate', 'selected', 'rejected')"),
        CheckConstraint("evidence_type IN ('literature', 'derived', 'placeholder')"),
    )
    id = Column(Integer, primary_key=True)
    factor_key = Column(String, nullable=False)
    version = Column(String, nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    value_decimal = Column(Text, nullable=False)
    unit = Column(String, nullable=False)
    method = Column(String, nullable=False)
    scope = Column(String, nullable=False)
    product_form = Column(String, nullable=False)
    production_system = Column(String, nullable=False)
    geography = Column(String, nullable=False, default="unknown")
    publication_year = Column(Integer)
    data_years_json = Column(Text, nullable=False, default="[]")
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    source_locator = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False)
    review_status = Column(String, nullable=False, default="candidate")
    usage_scope = Column(String, nullable=False)
    limitations_json = Column(Text, nullable=False, default="[]")
    carbon_accounting_json = Column(Text, nullable=False, default="{}")
    components_json = Column(Text)
    reviewed_at = Column(DateTime)
    review_note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class CalculationProfile(Base):
    __tablename__ = "calculation_profiles"
    __table_args__ = (
        UniqueConstraint("key", "version"),
        CheckConstraint("status IN ('draft', 'active', 'retired')"),
    )
    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False)
    version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    formula_version = Column(String, nullable=False)
    method = Column(String, nullable=False)
    scope = Column(String, nullable=False)
    usage_scope = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class ProfileFactor(Base):
    __tablename__ = "profile_factors"
    profile_id = Column(Integer, ForeignKey("calculation_profiles.id"), primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), primary_key=True)
    factor_id = Column(Integer, ForeignKey("material_factors.id"), nullable=False)
    selection_assumption = Column(Text, nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (Index("uq_analysis_request", "user_id", "client_request_id", unique=True),)
    result_kind = Column(String)
    formula_version = Column(String)
    profile_id = Column(Integer, ForeignKey("calculation_profiles.id"))
    snapshot_schema_version = Column(Integer)
    calculation_snapshot_json = Column(Text)
    client_request_id = Column(String)
    request_hash = Column(String)

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


def ensure_schema(target_engine=None):
    """Explicit, additive SQLite migration; never discard existing columns."""
    selected_engine = target_engine if target_engine is not None else engine
    with selected_engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        additions = {
            "analysis_results": {
                "user_id": "INTEGER", "carbon_footprint_min": "FLOAT",
                "carbon_footprint_max": "FLOAT", "min_weight_grams": "FLOAT",
                "max_weight_grams": "FLOAT", "unit": "VARCHAR DEFAULT 'kg CO2eq' NOT NULL",
                "raw_ocr_text": "TEXT", "unknown_materials": "TEXT DEFAULT '[]' NOT NULL",
                "created_at": "DATETIME", "result_kind": "VARCHAR",
                "formula_version": "VARCHAR", "profile_id": "INTEGER REFERENCES calculation_profiles(id)",
                "snapshot_schema_version": "INTEGER", "calculation_snapshot_json": "TEXT",
                "client_request_id": "VARCHAR", "request_hash": "VARCHAR",
            },
            "access_tokens": {"expires_at": "DATETIME"},
        }
        for table, columns in additions.items():
            existing = {row[1] for row in connection.exec_driver_sql(
                f"PRAGMA table_info({table})"
            ).fetchall()}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_request "
            "ON analysis_results(user_id, client_request_id)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
            "VALUES (1, CURRENT_TIMESTAMP)"
        )
        immutable_triggers = {
            "trg_selected_factor_no_update": """
                CREATE TRIGGER IF NOT EXISTS trg_selected_factor_no_update
                BEFORE UPDATE ON material_factors
                WHEN OLD.review_status = 'selected'
                BEGIN
                    SELECT RAISE(ABORT, 'selected material factor is immutable');
                END
            """,
            "trg_selected_factor_no_delete": """
                CREATE TRIGGER IF NOT EXISTS trg_selected_factor_no_delete
                BEFORE DELETE ON material_factors
                WHEN OLD.review_status = 'selected'
                BEGIN
                    SELECT RAISE(ABORT, 'selected material factor is immutable');
                END
            """,
            "trg_profile_insert_as_draft": """
                CREATE TRIGGER IF NOT EXISTS trg_profile_insert_as_draft
                BEFORE INSERT ON calculation_profiles
                WHEN NEW.status != 'draft'
                BEGIN
                    SELECT RAISE(ABORT, 'calculation profile must be created as draft');
                END
            """,
            "trg_profile_activation_requires_factors": """
                CREATE TRIGGER IF NOT EXISTS trg_profile_activation_requires_factors
                BEFORE UPDATE OF status ON calculation_profiles
                WHEN OLD.status = 'draft' AND NEW.status = 'active' AND (
                    NOT EXISTS (
                        SELECT 1 FROM profile_factors pf WHERE pf.profile_id = OLD.id
                    ) OR EXISTS (
                        SELECT 1
                        FROM profile_factors pf
                        LEFT JOIN material_factors mf ON mf.id = pf.factor_id
                        WHERE pf.profile_id = OLD.id AND (
                            mf.id IS NULL OR mf.material_id != pf.material_id
                            OR mf.review_status != 'selected'
                            OR mf.evidence_type NOT IN ('literature', 'derived')
                            OR mf.unit != 'kg CO2eq/kg fiber'
                            OR mf.method != NEW.method OR mf.scope != NEW.scope
                            OR mf.usage_scope != NEW.usage_scope
                            OR trim(pf.selection_assumption) = ''
                        )
                    )
                )
                BEGIN
                    SELECT RAISE(ABORT, 'calculation profile factors are incomplete or incompatible');
                END
            """,
            "trg_profile_activation_unique": """
                CREATE TRIGGER IF NOT EXISTS trg_profile_activation_unique
                BEFORE UPDATE OF status ON calculation_profiles
                WHEN OLD.status = 'draft' AND NEW.status = 'active' AND EXISTS (
                    SELECT 1 FROM calculation_profiles other
                    WHERE other.id != OLD.id AND other.status = 'active'
                      AND other.usage_scope = NEW.usage_scope
                )
                BEGIN
                    SELECT RAISE(ABORT, 'an active calculation profile already exists');
                END
            """,
            "trg_published_profile_no_rewrite": """
                CREATE TRIGGER IF NOT EXISTS trg_published_profile_no_rewrite
                BEFORE UPDATE ON calculation_profiles
                WHEN OLD.status IN ('active', 'retired') AND NOT (
                    OLD.status = 'active' AND NEW.status = 'retired'
                    AND NEW.key IS OLD.key AND NEW.version IS OLD.version
                    AND NEW.formula_version IS OLD.formula_version
                    AND NEW.method IS OLD.method AND NEW.scope IS OLD.scope
                    AND NEW.usage_scope IS OLD.usage_scope
                    AND NEW.created_at IS OLD.created_at
                )
                BEGIN
                    SELECT RAISE(ABORT, 'published calculation profile is immutable');
                END
            """,
            "trg_published_profile_no_delete": """
                CREATE TRIGGER IF NOT EXISTS trg_published_profile_no_delete
                BEFORE DELETE ON calculation_profiles
                WHEN OLD.status IN ('active', 'retired')
                BEGIN
                    SELECT RAISE(ABORT, 'published calculation profile is immutable');
                END
            """,
            "trg_published_profile_factor_no_insert": """
                CREATE TRIGGER IF NOT EXISTS trg_published_profile_factor_no_insert
                BEFORE INSERT ON profile_factors
                WHEN (SELECT status FROM calculation_profiles WHERE id = NEW.profile_id) != 'draft'
                BEGIN
                    SELECT RAISE(ABORT, 'published profile factors are immutable');
                END
            """,
            "trg_published_profile_factor_no_update": """
                CREATE TRIGGER IF NOT EXISTS trg_published_profile_factor_no_update
                BEFORE UPDATE ON profile_factors
                WHEN (SELECT status FROM calculation_profiles WHERE id = OLD.profile_id) != 'draft'
                BEGIN
                    SELECT RAISE(ABORT, 'published profile factors are immutable');
                END
            """,
            "trg_published_profile_factor_no_delete": """
                CREATE TRIGGER IF NOT EXISTS trg_published_profile_factor_no_delete
                BEFORE DELETE ON profile_factors
                WHEN (SELECT status FROM calculation_profiles WHERE id = OLD.profile_id) != 'draft'
                BEGIN
                    SELECT RAISE(ABORT, 'published profile factors are immutable');
                END
            """,
        }
        for trigger_sql in immutable_triggers.values():
            connection.exec_driver_sql(trigger_sql)
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
            "VALUES (2, CURRENT_TIMESTAMP)"
        )


if __name__ == "__main__":
    ensure_schema()
    print("Additive schema migration complete.")
