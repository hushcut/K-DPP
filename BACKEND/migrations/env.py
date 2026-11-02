"""Alembic 실행 환경.

DB 주소는 앱과 같은 곳(환경변수 K_DPP_DATABASE_URL → BACKEND/.env)에서 읽고,
표 정의는 database.Base.metadata 를 씁니다. PostgreSQL 만 받습니다(SQLite 는
마이그레이션 대상이 아님) — 옛 SQLite DB(k_dpp.db)에 실수로 돌리는 것을 막습니다.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

import database

config = context.config

# 테스트처럼 이미 로깅을 설정한 곳에서 부를 때는 attributes 로 끈다.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = database.Base.metadata

DATABASE_URL = database.SQLALCHEMY_DATABASE_URL
if make_url(DATABASE_URL).get_backend_name() != "postgresql":
    raise SystemExit(
        "Alembic 은 PostgreSQL 에만 돌립니다. K_DPP_DATABASE_URL 을 "
        "postgresql+psycopg://… 로 지정하세요(로컬은 BACKEND/compose.yaml)."
    )

COMPARE_OPTIONS = {"compare_type": True, "compare_server_default": True}


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` 처럼 DB 에 붙지 않고 SQL 만 뽑을 때."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMPARE_OPTIONS,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **COMPARE_OPTIONS,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
