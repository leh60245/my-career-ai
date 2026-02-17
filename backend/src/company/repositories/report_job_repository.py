from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ReportJobStatus
from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.company.models.report_job import ReportJob


class ReportJobRepository(BaseRepository[ReportJob]):
    def __init__(self, session: AsyncSession):
        super().__init__(ReportJob, session)

    async def get_by_company_id(self, company_id: int) -> Sequence[ReportJob]:
        stmt = select(self.model).where(self.model.company_id == company_id).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_jobs_by_status(self, status: ReportJobStatus) -> Sequence[ReportJob]:
        stmt = select(self.model).where(self.model.status == status.value).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_running_jobs_count(self) -> int:
        """
        현재 시스템 부하 확인용.
        PENDING이나 PROCESSING 상태인 작업의 개수를 셈.
        """
        from sqlalchemy import func, or_

        stmt = select(func.count()).where(
            or_(
                self.model.status == ReportJobStatus.PENDING.value,
                self.model.status == ReportJobStatus.PROCESSING.value,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_failed_jobs(self) -> Sequence[ReportJob]:
        stmt = (
            select(self.model)
            .where(self.model.status == ReportJobStatus.FAILED.value)
            .order_by(self.model.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """전체 Job 수를 반환합니다."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> Sequence[ReportJob]:
        """최신 순으로 Job 목록을 반환합니다."""
        stmt = select(self.model).order_by(self.model.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
