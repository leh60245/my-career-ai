"""
CompanyTalent Repository

기업 인재상 데이터의 CRUD 및 조회 로직.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.company.models.talent import CompanyTalent


logger = logging.getLogger(__name__)


class CompanyTalentRepository(BaseRepository[CompanyTalent]):
    """기업 인재상 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CompanyTalent, session)

    async def get_by_company_id(self, company_id: int, year: int | None = None) -> Sequence[CompanyTalent]:
        """
        기업 ID로 인재상 데이터를 조회한다.

        Args:
            company_id: 기업 PK
            year: 특정 연도 필터 (None이면 전체)

        Returns:
            인재상 목록 (최신순)
        """
        stmt = select(self.model).where(self.model.company_id == company_id)

        if year is not None:
            stmt = stmt.where(self.model.year == year)

        stmt = stmt.order_by(self.model.year.desc().nulls_last())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_by_company_id(self, company_id: int) -> CompanyTalent | None:
        """
        기업의 최신 인재상 데이터를 반환한다.

        Args:
            company_id: 기업 PK

        Returns:
            최신 인재상 또는 None
        """
        stmt = (
            select(self.model)
            .where(self.model.company_id == company_id)
            .order_by(self.model.year.desc().nulls_last())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
