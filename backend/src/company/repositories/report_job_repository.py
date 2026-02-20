import logging
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ReportJobStatus
from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.company.models.report_job import ReportJob


logger = logging.getLogger(__name__)


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
            .where(self.model.status == ReportJobStatus.PENDING.value, self.model.user_id.is_not(None))
            .order_by(self.model.created_at.asc())  # 먼저 요청된 것부터
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def check_duplicate_request(
        self, user_id: int, company_id: int | None, company_name: str
    ) -> ReportJob | None:
        """
        사용자의 동일 기업에 대한 기존 요청이 있는지 확인.
        PENDING(대기), PROCESSING(진행), COMPLETED(완료) 상태의 요청을 확인.
        REJECTED와 FAILED는 무시.

        company_id가 None이면 company_name으로 중복 검사한다 (DB에 없는 기업 케이스).
        """
        from sqlalchemy import and_, or_

        company_filter = (
            self.model.company_id == company_id if company_id is not None else self.model.company_name == company_name
        )

        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.user_id == user_id,
                    company_filter,
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

    async def get_stuck_processing_jobs(self) -> Sequence[ReportJob]:
        """
        서버 재시작 전 PROCESSING 상태로 남아있던 (중단된) 잡을 모두 반환한다.

        서버가 정상 종료되지 않은 경우 PROCESSING 상태의 잡이 영구적으로 stuck 될 수 있다.
        lifespan 시작 시점에 호출하여 복구 처리에 사용한다.
        """
        stmt = select(self.model).where(self.model.status == ReportJobStatus.PROCESSING.value)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def bulk_mark_failed(self, job_ids: list[str], error_message: str) -> int:
        """
        주어진 job_id 목록을 일괄적으로 FAILED 상태로 변경한다.

        Args:
            job_ids: 실패 처리할 job_id 목록
            error_message: 에러 메시지

        Returns:
            실제로 업데이트된 행 수
        """
        if not job_ids:
            return 0

        from datetime import UTC, datetime

        stmt = (
            update(self.model)
            .where(self.model.id.in_(job_ids))
            .values(
                status=ReportJobStatus.FAILED.value, error_message=error_message[:2000], updated_at=datetime.now(UTC)
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount
