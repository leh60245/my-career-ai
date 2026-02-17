from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.company.models.generated_report import GeneratedReport


class GeneratedReportRepository(BaseRepository[GeneratedReport]):
    def __init__(self, session: AsyncSession):
        super().__init__(GeneratedReport, session)

    async def get_by_job_id(self, job_id: str) -> GeneratedReport | None:
        stmt = select(self.model).where(self.model.job_id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_company_name(self, company_name: str) -> Sequence[GeneratedReport]:
        """특정 기업명의 모든 생성 리포트를 최신순으로 조회한다."""
        stmt = select(self.model).where(self.model.company_name == company_name).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()
