from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import AnalysisReportStatus
from src.models import AnalysisReport
from src.repositories.base_repository import BaseRepository


class AnalysisReportRepository(BaseRepository[AnalysisReport]):
    def __init__(self, session: AsyncSession):
        super().__init__(AnalysisReport, session)

    async def get_by_company_id(self, company_id: int) -> Sequence[AnalysisReport]:
        stmt = select(self.model).where(self.model.company_id == company_id).order_by(self.model.rcept_dt.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_rcept_no(self, rcept_no: str) -> AnalysisReport | None:
        stmt = select(self.model).where(self.model.rcept_no == rcept_no)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_company_id(self, company_id: int) -> AnalysisReport | None:
        stmt = (
            select(AnalysisReport)
            .where(AnalysisReport.company_id == company_id)
            .order_by(AnalysisReport.rcept_dt.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_processing_failed_reports(self) -> Sequence[AnalysisReport]:
        stmt = select(self.model).where(self.model.status == AnalysisReportStatus.FAILED)
        result = await self.session.execute(stmt)
        return result.scalars().all()
