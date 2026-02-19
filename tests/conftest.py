"""
pytest 공용 픽스처 모음

테스트 전략:
- 실제 PostgreSQL 기반 통합 테스트 (pgvector, JSONB 등 비표준 타입 호환성 필요)
- 각 테스트는 SAVEPOINT(중첩 트랜잭션)로 감싸고 종료 시 ROLLBACK 수행
- 개발/운영 DB에 데이터가 잔류하지 않음
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.main import app
from backend.src.common.config import DB_CONFIG


# ============================================================
# 1. Database URL (테스트 전용 — 같은 PostgreSQL 서버 사용)
# ============================================================
def _build_test_url() -> str:
    user = DB_CONFIG["user"]
    password = DB_CONFIG["password"]
    host = DB_CONFIG["host"]
    port = DB_CONFIG["port"]
    database = DB_CONFIG["database"]
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


TEST_DATABASE_URL = _build_test_url()


# ============================================================
# 2. 엔진 & 세션 픽스처 (세션 스코프 — 모든 테스트 공유)
# ============================================================
@pytest_asyncio.fixture
async def engine():
    """테스트 전용 비동기 엔진 (함수 스코프 — 각 테스트마다 독립 생성)."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield _engine
    await _engine.dispose()


# ============================================================
# 3. 각 테스트를 트랜잭션으로 격리 (핵심 픽스처)
# ============================================================
@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    각 테스트 함수마다 새로운 격리된 AsyncSession 제공.

    SAVEPOINT(중첩 트랜잭션) 방식으로 테스트 종료 시 모든 변경사항을 ROLLBACK.
    실제 DB에 데이터가 잔류하지 않도록 보장.
    """
    async with engine.connect() as conn:
        await conn.begin()
        await conn.begin_nested()  # SAVEPOINT 생성

        session_factory = async_sessionmaker(
            bind=conn, class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False
        )
        async_session = session_factory()

        try:
            yield async_session
        finally:
            await async_session.close()
            await conn.rollback()  # SAVEPOINT & 외부 트랜잭션 모두 롤백


# ============================================================
# 4. FastAPI TestClient (세션 오버라이드 포함)
# ============================================================
@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI 앱의 AsyncClient.

    모든 라우터의 get_session 의존성을 테스트 세션으로 교체.
    """
    from backend.src.company.router import get_session as company_get_session
    from backend.src.resume.router import get_session as resume_get_session
    from backend.src.user.router import get_session as user_get_session

    async def override_get_session():
        yield session

    app.dependency_overrides[company_get_session] = override_get_session
    app.dependency_overrides[resume_get_session] = override_get_session
    app.dependency_overrides[user_get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================
# 5. 공통 테스트 데이터 픽스처
# ============================================================
@pytest_asyncio.fixture
async def job_seeker_user(session: AsyncSession) -> Any:
    """
    구직자 사용자 픽스처.

    테스트에서 재사용 가능한 일반 사용자(JOB_SEEKER) 생성.
    """
    from backend.src.common.enums import UserRole
    from backend.src.user.models import User

    user = User(email="jobseeker_test@example.com", role=UserRole.JOB_SEEKER)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_user(session: AsyncSession) -> Any:
    """
    관리자 사용자 픽스처.

    RBAC 테스트에서 사용하는 관리자(MANAGER) 계정.
    """
    from backend.src.common.enums import UserRole
    from backend.src.user.models import User

    user = User(email="manager_test@example.com", role=UserRole.MANAGER)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_company(session: AsyncSession) -> Any:
    """
    테스트 기업 픽스처.

    기업 분석 요청 등에서 사용하는 테스트 기업 데이터.
    """
    from backend.src.company.models.company import Company

    company = Company(
        company_name="테스트기업주식회사",
        corp_code="99999999",
        stock_code=None,
        industry_code="J",
        sector="소프트웨어",
        product="테스트제품",
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company
