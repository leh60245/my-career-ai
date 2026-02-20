import logging
import uuid
from collections.abc import Sequence
from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ReportJobStatus
from backend.src.company.models.report_job import ReportJob
from backend.src.company.repositories.report_job_repository import ReportJobRepository


logger = logging.getLogger(__name__)


class ReportJobService:
    """
    리포트 생성 작업(Job)의 생명주기(Lifecycle)를 관리하는 서비스
    """

    def __init__(self, repository: ReportJobRepository):
        self.repository = repository

    @classmethod
    def from_session(cls, session: AsyncSession) -> "ReportJobService":
        """AsyncSession으로부터 서비스 인스턴스 생성 (Controller용)"""
        return cls(ReportJobRepository(session))

    async def create_job(self, company_id: int, company_name: str, topic: str) -> str:
        """
        새로운 작업을 생성하고 PENDING 상태로 초기화합니다.
        Returns: 생성된 job_id
        """
        job_id = str(uuid.uuid4())

        job_data = {
            "id": job_id,
            "company_id": company_id,
            "company_name": company_name,
            "topic": topic,
            "status": ReportJobStatus.PENDING,
            # created_at은 TimestampMixin이 자동 설정 (server_default=func.now())
            "error_message": None,
        }

        await self.repository.create(job_data)
        logger.info(f"Job Created: {job_id} ({company_name} - {topic})")
        return job_id

    async def start_job(self, job_id: str) -> None:
        """작업 상태를 PROCESSING으로 변경"""
        await self.repository.update(job_id, {"status": ReportJobStatus.PROCESSING})
        logger.info(f"Job Started: {job_id}")

    async def complete_job(self, job_id: str) -> None:
        """작업 상태를 COMPLETED로 변경"""
        await self.repository.update(
            job_id,
            {
                "status": ReportJobStatus.COMPLETED,
                "error_message": None,  # 성공했으니 에러 메시지는 클리어 (선택사항)
            },
        )
        logger.info(f" Job Completed: {job_id}")

    async def fail_job(self, job_id: str, error_message: str) -> None:
        """
        [핵심] 작업 상태를 FAILED로 변경하고 에러 원인을 기록
        """
        # 에러 메시지가 너무 길면 DB 컬럼 제한에 걸릴 수 있으므로 안전하게 자름 (예: 2000자)
        safe_message = error_message[:2000] if error_message else "Unknown Error"

        await self.repository.update(job_id, {"status": ReportJobStatus.FAILED, "error_message": safe_message})
        logger.error(f"Job Failed: {job_id} - {safe_message}")

    async def get_job(self, job_id: str) -> ReportJob | None:
        """작업 상세 조회"""
        return await self.repository.get(job_id)

    async def get_company_jobs(self, company_id: int) -> Sequence[ReportJob]:
        """특정 회사의 모든 작업 이력 조회"""
        return await self.repository.get_by_company_id(company_id)

    async def get_failed_jobs(self) -> Sequence[ReportJob]:
        """실패한 모든 작업 조회"""
        return await self.repository.get_failed_jobs()

    async def list_jobs(self, *, limit: int = 20, offset: int = 0) -> tuple[int, list[ReportJob]]:
        """
        최신 순으로 작업 목록을 조회합니다.
        Returns: (전체 건수, 페이지 결과)
        """
        total = await self.repository.count()
        jobs = await self.repository.list_recent(limit=limit, offset=offset)
        return total, list(jobs)

    # ============================================================
    # 기업 분석 요청 플로우 (구직자 <-> 관리자)
    # ============================================================

    async def submit_analysis_request(self, user_id: int, company_id: int | None, company_name: str, topic: str) -> str:
        """
        구직자의 기업 분석 요청 등록.

        중복 요청 방지: 동일 기업에 대한 미완료 요청이 있으면 DuplicateEntity 예외 발생.

        Args:
            user_id: 요청한 구직자의 user_id
            company_id: 분석을 요청한 기업의 company_id
            company_name: 기업명
            topic: 분석 주제

        Returns:
            생성된 job_id

        Raises:
            DuplicateEntity: 동일 기업에 대한 미완료 요청이 있을 경우
        """
        from datetime import datetime

        # 중복 요청 확인
        existing = await self.repository.check_duplicate_request(user_id, company_id, company_name)
        if existing:
            from backend.src.common.repositories.base_repository import DuplicateEntity

            raise DuplicateEntity(
                f"동일 기업에 대한 요청이 이미 진행 중입니다 (상태: {existing.status}, ID: {existing.id})"
            )

        # 새로운 분석 요청 생성
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        job_data = {
            "id": job_id,
            "company_id": company_id,
            "company_name": company_name,
            "topic": topic,
            "status": ReportJobStatus.PENDING,
            "user_id": user_id,
            "requested_at": now,
            "error_message": None,
        }

        await self.repository.create(job_data)
        logger.info(f"Analysis Request Created: {job_id} ({company_name} - {topic}) by user_id={user_id}")
        return job_id

    async def approve_request(self, job_id: str, approved_by_user_id: int) -> None:
        """
        관리자의 분석 요청 승인.

        Args:
            job_id: 승인할 요청 ID
            approved_by_user_id: 승인한 관리자의 user_id

        Raises:
            EntityNotFound: 요청이 없거나 이미 처리된 경우
        """
        from datetime import datetime

        job = await self.repository.get(job_id)
        if not job:
            from backend.src.common.repositories.base_repository import EntityNotFound

            raise EntityNotFound(f"Job not found: {job_id}")

        if job.status != ReportJobStatus.PENDING:
            from backend.src.common.repositories.base_repository import EntityNotFound

            raise EntityNotFound(f"Job is not in PENDING state: {job_id} (status: {job.status})")

        now = datetime.now(UTC)
        await self.repository.update(
            job_id, {"status": ReportJobStatus.PROCESSING, "approved_by": approved_by_user_id, "approved_at": now}
        )
        logger.info(f"Analysis Request Approved: {job_id} by admin_id={approved_by_user_id}")

    async def reject_request(self, job_id: str, approved_by_user_id: int, rejection_reason: str) -> None:
        """
        관리자의 분석 요청 반려.

        Args:
            job_id: 반려할 요청 ID
            approved_by_user_id: 반려한 관리자의 user_id
            rejection_reason: 반려 사유

        Raises:
            EntityNotFound: 요청이 없거나 이미 처리된 경우
        """
        from datetime import datetime

        job = await self.repository.get(job_id)
        if not job:
            from backend.src.common.repositories.base_repository import EntityNotFound

            raise EntityNotFound(f"Job not found: {job_id}")

        if job.status != ReportJobStatus.PENDING:
            from backend.src.common.repositories.base_repository import EntityNotFound

            raise EntityNotFound(f"Job is not in PENDING state: {job_id} (status: {job.status})")

        now = datetime.now(UTC)
        await self.repository.update(
            job_id,
            {
                "status": ReportJobStatus.REJECTED,
                "approved_by": approved_by_user_id,
                "rejected_at": now,
                "rejection_reason": rejection_reason,
            },
        )
        logger.info(f"Analysis Request Rejected: {job_id} by admin_id={approved_by_user_id} - {rejection_reason}")

    async def get_user_requests(self, user_id: int) -> Sequence[ReportJob]:
        """
        구직자의 모든 분석 요청 조회.

        Args:
            user_id: 구직자의 user_id

        Returns:
            사용자의 분석 요청 목록 (최신순)
        """
        return await self.repository.get_by_user_id(user_id)

    async def get_pending_requests(self) -> Sequence[ReportJob]:
        """
        관리자용: 승인 대기 중인 모든 분석 요청 조회.

        Returns:
            승인 대기 중인 요청 목록 (먼저 요청된 순)
        """
        return await self.repository.get_pending_requests()

    async def recover_interrupted_jobs(self) -> int:
        """
        서버 재시작 시 PROCESSING 상태로 남아있는 중단된 잡을 FAILED로 복구한다.

        Ctrl+C, 서버 강제 종료, 프로세스 크래시 등으로 인해 PROCESSING 상태에서
        정상 완료 처리가 되지 않은 잡들을 탐지하고 FAILED로 전환한다.

        Returns:
            복구된 잡의 수
        """
        stuck_jobs = await self.repository.get_stuck_processing_jobs()
        if not stuck_jobs:
            return 0

        job_ids = [job.id for job in stuck_jobs]
        count = await self.repository.bulk_mark_failed(
            job_ids, error_message="서버 재시작으로 인한 분석 중단. 관리자에게 재요청 또는 재시도가 필요합니다."
        )
        logger.warning("서버 재시작 후 중단된 잡 %d개를 FAILED로 복구: %s", count, job_ids)
        return count
