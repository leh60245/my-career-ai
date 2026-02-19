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

    async def get_by_user_id(self, user_id: int) -> Sequence[ReportJob]:
        """특정 사용자가 요청한 모든 분석 요청 조회."""
        stmt = select(self.model).where(self.model.user_id == user_id).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_pending_requests(self) -> Sequence[ReportJob]:
        """관리자용: 대기 중인 분석 요청 조회 (승인 대기 상태)."""
        stmt = (
            select(self.model)
            .where(self.model.status == ReportJobStatus.PENDING.value)
            .order_by(self.model.created_at.asc())  # 먼저 요청된 것부터
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def check_duplicate_request(self, user_id: int, company_id: int) -> ReportJob | None:
        """
        사용자의 동일 기업에 대한 기존 요청이 있는지 확인.
        PENDING(대기), PROCESSING(진행), COMPLETED(완료) 상태의 요청을 확인.
        REJECTED와 FAILED는 무시.
        """
        from sqlalchemy import and_, or_

        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.user_id == user_id,
                    self.model.company_id == company_id,
                    or_(
                        self.model.status == ReportJobStatus.PENDING.value,
                        self.model.status == ReportJobStatus.PROCESSING.value,
                        self.model.status == ReportJobStatus.COMPLETED.value,
                    ),
                )
            )
            .order_by(self.model.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
