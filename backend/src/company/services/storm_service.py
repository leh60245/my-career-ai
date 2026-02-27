import logging
from typing import Any

from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.enums import ReportJobStatus

from .company_service import CompanyService
from .report_job_service import ReportJobService


logger = logging.getLogger(__name__)

# ============================================================
# In-Memory Job State (프론트엔드 polling용)
# ============================================================
# DB에도 상태가 기록되지만, 실시간 progress(%) 같은 세밀한 정보는
# 메모리에서 관리하고 프론트엔드가 빠르게 조회할 수 있게 합니다.
JOBS: dict[str, dict[str, Any]] = {}


class StormService:
    """
    FastAPI Background Task에서 호출되는 서비스 클래스.
    JOBS dict 초기화 → 파이프라인 위임 → 결과 반영.
    """

    def __init__(self) -> None:
        self.db_engine = AsyncDatabaseEngine()

    async def create_job(self, company_name: str, topic: str) -> str:
        """
        DB에 Job 레코드를 생성하고, JOBS dict에 초기 상태를 등록합니다.
        Returns: job_id (UUID)
        """
        async with self.db_engine.get_session() as session:
            # Service 계층을 통한 Company 조회
            company_service = CompanyService.from_session(session)
            company = await company_service.get_by_name(company_name)
            if not company:
                raise ValueError(f"Company '{company_name}' not found in DB")

            # Service 계층을 통한 Job 생성
            job_service = ReportJobService.from_session(session)
            job_id = await job_service.create_job(company_id=company.id, company_name=company_name, topic=topic)

        # 메모리 상태 초기화
        JOBS[job_id] = {
            "status": ReportJobStatus.PENDING.value,
            "progress": 0,
            "message": "작업이 생성되었습니다.",
            "report_id": None,
        }

        logger.info(f"[StormService] Job registered: {job_id} ({company_name})")
        return job_id

    async def run_pipeline(self, job_id: str, company_name: str, topic: str, model_provider: str = "openai") -> None:
        """
        Background Task로 실행됩니다.
        Career Pipeline(고정 페르소나 기반)에 모든 실행을 위임합니다.

        변경사항 (v1.1):
            - 기존 STORMWikiRunner 기반 동적 파이프라인을 완전히 우회합니다.
            - 고정 3 페르소나 + 하드코딩 쿼리 큐 기반 Career Pipeline을 사용합니다.
            - LLM 출력은 Markdown이 아닌 순수 JSON 형태입니다.
        """
        logger.info(f"[StormService] Career Pipeline 위임: job {job_id} ({company_name})")

        try:
            # Lazy import: 무거운 의존성을 실행 시점에만 로드합니다.
            from backend.src.company.engine.career_pipeline import run_career_pipeline

            await run_career_pipeline(
                job_id=job_id, company_name=company_name, topic=topic, jobs_dict=JOBS, model_provider=model_provider
            )
        except Exception as e:
            logger.error(f"[StormService] Pipeline failed for {job_id} ({company_name}): {e}")
            if job_id in JOBS:
                JOBS[job_id]["status"] = ReportJobStatus.FAILED.value
                JOBS[job_id]["message"] = str(e)
                JOBS[job_id]["progress"] = 0

    async def run_legacy_pipeline(
        self, job_id: str, company_name: str, topic: str, model_provider: str = "openai"
    ) -> None:
        """
        [레거시] 기존 STORMWikiRunner 기반 파이프라인.
        하위 호환성 유지 또는 비교 테스트 용도로만 사용합니다.
        """
        logger.info(f"[StormService] Legacy STORM Pipeline 위임: job {job_id} ({company_name})")

        try:
            from backend.src.company.engine.storm_pipeline import run_storm_pipeline

            await run_storm_pipeline(
                job_id=job_id, company_name=company_name, topic=topic, jobs_dict=JOBS, model_provider=model_provider
            )
        except Exception as e:
            logger.error(f"[StormService] Legacy pipeline failed for {job_id} ({company_name}): {e}")
            if job_id in JOBS:
                JOBS[job_id]["status"] = ReportJobStatus.FAILED.value
                JOBS[job_id]["message"] = str(e)
                JOBS[job_id]["progress"] = 0

    @staticmethod
    def get_job_status_from_memory(job_id: str) -> dict[str, Any] | None:
        """
        메모리에서 실시간 진행률을 조회합니다.
        없으면 None (DB 폴백은 API 레이어에서 처리).
        """
        return JOBS.get(job_id)

    @staticmethod
    def get_all_jobs() -> dict[str, dict[str, Any]]:
        """현재 메모리에 등록된 모든 Job 상태 반환."""
        return JOBS
