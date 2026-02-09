import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# [수정 2] .env 파일 로드 (이게 없으면 os.getenv가 아무것도 못 가져옵니다)
load_dotenv()

logger = logging.getLogger(__name__)
Base = declarative_base()

# 환경 변수 설정
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")  # .env가 로드되어야 값을 가져옴
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

# [안전장치] 비밀번호가 없으면 연결 시도 전에 알려줌
if not DB_PASSWORD:
    # 로컬 개발 편의를 위해 하드코딩된 fallback을 쓸 수도 있지만,
    # 명시적으로 에러를 내는 것이 설정 실수를 잡기 좋습니다.
    # 하지만 님 상황(1234)에 맞춰 fallback을 넣어드리겠습니다.
    logger.warning("⚠️ DB_PASSWORD not found in env. Using default '1234'.")
    DB_PASSWORD = "1234"

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
