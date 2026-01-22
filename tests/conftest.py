"""
Pytest Configuration and Shared Fixtures

Refactored:
- Added `await db_session.refresh(company)` to fixture to prevent stale object access.
- Retained UUID generation for unique companies.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncDatabaseEngine
from src.database.models import Company

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ... (Configuration, Event Loop, DB Engine, Session fixtures remain same) ...
# (중복을 피하기 위해 변경된 부분만 아래에 표시합니다. 위에서부터 덮어쓰셔도 됩니다.)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")


@pytest.fixture(scope="function")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    with contextlib.suppress(Exception):
        loop.close()


@pytest.fixture(scope="function")
async def db_engine():
    """
    [Modified] Singleton 강제 초기화 코드를 제거했습니다.
    AsyncDatabaseEngine.dispose()가 내부적으로 싱글톤 인스턴스를 정리합니다.
    """
    logger.info("Initializing test database engine...")

    # Singleton 인스턴스 획득 및 초기화
    engine = AsyncDatabaseEngine()
    await engine.initialize(echo=False)

    yield engine

    logger.info("Disposing test database engine...")
    # [Refactor] dispose() 호출 시 _instance = None 및 리소스 정리가 자동 수행됨
    await engine.dispose()


@pytest.fixture
async def db_session(
    db_engine: AsyncDatabaseEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Creates a fresh SQLAlchemy session for a test.
    Rolls back transaction after test to ensure isolation.
    """
    async with db_engine.get_session() as session:
        yield session
        # 테스트 종료 후 롤백 (데이터 오염 방지)
        await session.rollback()


# ===== Test Data Fixtures (FIXED) =====


@pytest.fixture
def test_company_data() -> dict:
    """Provide sample company data with UNIQUE name."""
    unique_id = uuid.uuid4().hex[:8]
    # [Check] is_active 필드는 Phase 3에서 제거되었으므로 포함하지 않음
    return {
        "company_name": f"테스트_삼성전자_{unique_id}",
        "corp_code": "005930",
        "stock_code": "005930",
        "industry": "Semiconductor",
    }


@pytest.fixture
async def test_company(db_session: AsyncSession, test_company_data: dict) -> Company:
    """Create a test company in the database."""
    from src.database.repositories import CompanyRepository

    repo = CompanyRepository(db_session)

    # 중복 방지 (혹시 이전 테스트 데이터가 남았을 경우)
    existing = await repo.get_by_name(test_company_data["company_name"])
    if existing:
        return existing

    company = await repo.create(test_company_data)
    await db_session.commit()

    # [Fix] Refresh the object so attributes are loaded and usable in tests
    await db_session.refresh(company)

    return company


# ===== Utility Fixtures =====


@pytest.fixture
def cleanup_test_data():
    async def _cleanup(session: AsyncSession, model, **filters):
        from sqlalchemy import delete

        stmt = delete(model).where(
            *[
                getattr(model, k).like(v)
                if "%" in str(v) or "*" in str(v)
                else getattr(model, k) == v
                for k, v in filters.items()
            ]
        )
        await session.execute(stmt)
        await session.commit()

    return _cleanup
