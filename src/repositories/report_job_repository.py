from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common import ReportJobStatus
from src.models import ReportJob
from src.repositories import BaseRepository


class ReportJobRepository(BaseRepository[ReportJob]):
    def __init__(self, session: AsyncSession):
        super().__init__(ReportJob, session)

    async def get_by_company_id(self, company_id: int) -> Sequence[ReportJob]:
        stmt = select(self.model).where(self.model.company_id == company_id).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_jobs_by_status(self, status: ReportJobStatus) -> Sequence[ReportJob]:
        stmt = select(self.model).where(self.model.status == status).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_running_jobs_count(self) -> int:
        """
        현재 시스템 부하 확인용.
        PENDING이나 PROCESSING 상태인 작업의 개수를 셈.
        """
        from sqlalchemy import func, or_

        stmt = select(func.count()).where(
            or_(self.model.status == ReportJobStatus.PENDING, self.model.status == ReportJobStatus.PROCESSING)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
