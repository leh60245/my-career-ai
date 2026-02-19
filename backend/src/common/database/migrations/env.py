from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# sys.path에 프로젝트 루트 디렉토리 추가 (절대 임포트 지원)
# __file__ = .../backend/src/common/database/migrations/env.py
# parents[4] = .../backend/, parents[5] = .../ (프로젝트 루트)
project_root = Path(__file__).resolve().parents[5]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.src.common.config import DB_CONFIG
from backend.src.common.models.base import Base

# 모델 임포트 (metadata 등록용)
from backend.src.common.models import job as common_job_models  # noqa: F401
from backend.src.company import models as company_models  # noqa: F401
from backend.src.resume import models as resume_models  # noqa: F401
from backend.src.user import models as user_models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def _build_database_url() -> str:
    """DB 설정으로부터 Alembic용 URL을 생성합니다."""
    user = DB_CONFIG["user"]
    password = DB_CONFIG["password"]
    host = DB_CONFIG["host"]
    port = DB_CONFIG["port"]
    database = DB_CONFIG["database"]
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def run_migrations_offline() -> None:
    """오프라인 모드에서 마이그레이션을 실행합니다."""
    url = _build_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인(비동기) 모드에서 마이그레이션을 실행합니다."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = _build_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
