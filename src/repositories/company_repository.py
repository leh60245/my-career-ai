import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Company
from src.repositories.base_repository import BaseRepository, RepositoryError

logger = logging.getLogger(__name__)


class CompanyRepository(BaseRepository[Company]):
    def __init__(self, session: AsyncSession):
        super().__init__(Company, session)

    async def get_by_company_name(self, company_name: str) -> Company | None:
        stmt = select(self.model).where(self.model.company_name == company_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_corp_code(self, corp_code: str) -> Company | None:
        stmt = select(self.model).where(self.model.corp_code == corp_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_stock_code(self, stock_code: str) -> Company | None:
        stmt = select(self.model).where(self.model.stock_code == stock_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_industry_code(self, industry_code: str) -> Sequence[Company]:
        stmt = select(self.model).where(self.model.industry_code == industry_code)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_all_companies_for_cache(self) -> Sequence[Company]:
        """캐싱을 위해 제약 없이 모든 기업 정보 로드"""
        stmt = select(self.model)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_by_company_name(self, query: str, limit: int = 10) -> Sequence[Company]:
        """기업 이름으로 부분 일치 검색"""
        try:
            search_term = f"%{query}%"
            stmt = select(self.model).where(self.model.company_name.ilike(search_term)).limit(limit)
            result = await self.session.execute(stmt)
            companies = result.scalars().all()
            logger.debug(f"Search for '{query}' returned {len(companies)} results")
            return companies

        except Exception as e:
            logger.error(f"Error searching companies for '{query}': {e}")
            raise RepositoryError(f"Failed to search companies: {e}") from e
