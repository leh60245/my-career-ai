import logging
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from src.common.enums import ReportJobStatus
from src.company_analysis.models.report_job import ReportJob
from src.company_analysis.repositories.report_job_repository import ReportJobRepository


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
            "error_message": None
        }

        await self.repository.create(job_data)
        logger.info(f"🆕 Job Created: {job_id} ({company_name} - {topic})")
        return job_id

    async def start_job(self, job_id: str) -> None:
        """작업 상태를 PROCESSING으로 변경"""
        await self.repository.update(job_id, {"status": ReportJobStatus.PROCESSING})
        logger.info(f"▶️ Job Started: {job_id}")

    async def complete_job(self, job_id: str) -> None:
        """작업 상태를 COMPLETED로 변경"""
        await self.repository.update(
            job_id,
            {
                "status": ReportJobStatus.COMPLETED,
                "error_message": None # 성공했으니 에러 메시지는 클리어 (선택사항)
            }
        )
        logger.info(f"✅ Job Completed: {job_id}")

    async def fail_job(self, job_id: str, error_message: str) -> None:
        """
        [핵심] 작업 상태를 FAILED로 변경하고 에러 원인을 기록
        """
        # 에러 메시지가 너무 길면 DB 컬럼 제한에 걸릴 수 있으므로 안전하게 자름 (예: 2000자)
        safe_message = error_message[:2000] if error_message else "Unknown Error"

        await self.repository.update(
            job_id,
            {
                "status": ReportJobStatus.FAILED,
                "error_message": safe_message
            }
        )
        logger.error(f"❌ Job Failed: {job_id} - {safe_message}")

    async def get_job(self, job_id: str) -> ReportJob | None:
        """작업 상세 조회"""
        return await self.repository.get(job_id)

    async def get_company_jobs(self, company_id: int) -> Sequence[ReportJob]:
        """특정 회사의 모든 작업 이력 조회"""
        return await self.repository.get_by_company_id(company_id)

    async def get_failed_jobs(self) -> Sequence[ReportJob]:
        """실패한 모든 작업 조회"""
        return await self.repository.get_failed_jobs()

    async def list_jobs(
        self, *, limit: int = 20, offset: int = 0
    ) -> tuple[int, list[ReportJob]]:
        """
        최신 순으로 작업 목록을 조회합니다.
        Returns: (전체 건수, 페이지 결과)
        """
        total = await self.repository.count()
        jobs = await self.repository.list_recent(limit=limit, offset=offset)
        return total, list(jobs)
