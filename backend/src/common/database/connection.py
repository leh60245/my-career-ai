import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from src.common.models.base import Base


# .env 파일 로드
load_dotenv()

logger = logging.getLogger(__name__)

# 환경 변수 설정
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


class AsyncDatabaseEngine:
    """
    SQLAlchemy AsyncIO 엔진 래퍼 (Singleton Pattern)
    """

    _instance: Optional["AsyncDatabaseEngine"] = None
    session_factory: async_sessionmaker | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 이미 초기화되었다면 스킵 (Singleton)
        if hasattr(self, "engine") and self.engine is not None:
            return

        self.engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10,
            pool_recycle=3600,
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        logger.info(f"✅ AsyncDatabaseEngine initialized: {DB_HOST}:{DB_PORT}/{DB_NAME}")

    async def initialize(self) -> None:
        """
        FastAPI lifespan에서 호출하는 초기화 메서드.
        엔진은 __init__에서 이미 생성되므로,
        여기서는 연결 확인 + 풀 워밍업 + 선택적 스키마 생성을 처리합니다.
        """
        # 커넥션 풀 워밍업: 첫 API 요청 시 지연을 방지
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection pool warmed up")
        except Exception as e:
            logger.warning(f"⚠️ DB warmup failed (will retry on first request): {e}")

        if os.getenv("AUTO_CREATE_SCHEMA") == "1":
            logger.warning("⚠️ AUTO_CREATE_SCHEMA=1: Creating DB schema from models.")
            await ensure_schema()

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        [Context Manager] async with db.get_session() as session:
        """
        if self.session_factory is None:
            raise RuntimeError("Database SessionFactory is not initialized.")

        session: AsyncSession = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Session rollback due to exception: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self):
        """커넥션 풀 종료"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            AsyncDatabaseEngine._instance = None
            logger.info("🗑️ AsyncDatabaseEngine disposed.")


async def ensure_schema(reset: bool = False) -> None:
    """
    Alembic 없이 모델 기반으로 스키마를 생성합니다.
    개발/테스트 환경에서만 사용하세요.
    """
    # 모델 등록을 위해 임포트 (Base.metadata 채우기)
    from src.company_analysis.models import analysis_report, company, generated_report, report_job, source_material  # noqa: F401

    db = AsyncDatabaseEngine()
    async with db.engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

def create_isolated_engine() -> AsyncEngine:

    db_url = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    return create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        # 스레드마다 별도 연결이므로 풀 사이즈를 작게 유지
        pool_size=2,
        max_overflow=5
    )
