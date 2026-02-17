"""
Company 도메인 API 라우터

기업 정보 조회, STORM 리포트 생성/조회, 작업 상태 폴링 등
기업 분석 도메인의 모든 HTTP 엔드포인트를 관리한다.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.config import TOPICS
from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.company.schemas.company import CompanyResponse
from backend.src.company.schemas.generated_report import (
    GeneratedReportListItem,
    GeneratedReportResponse,
    GenerateReportRequest,
)
from backend.src.company.schemas.report_job import ReportJobResponse, ReportListResponse, ReportSummary
from backend.src.company.services.company_service import CompanyService
from backend.src.company.services.generated_report_service import GeneratedReportService
from backend.src.company.services.report_job_service import ReportJobService
from backend.src.company.services.storm_service import StormService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["company"])

# StormService는 모듈 레벨 싱글턴 (Background Task용 자체 세션 관리)
storm_service = StormService()


# ============================================================
# Dependencies
# ============================================================
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공."""
    db_engine = AsyncDatabaseEngine()
    async with db_engine.get_session() as session:
        yield session


async def get_company_service(session: AsyncSession = Depends(get_session)) -> CompanyService:
    """CompanyService 팩토리."""
    return CompanyService.from_session(session)


async def get_report_job_service(session: AsyncSession = Depends(get_session)) -> ReportJobService:
    """ReportJobService 팩토리."""
    return ReportJobService.from_session(session)


async def get_generated_report_service(session: AsyncSession = Depends(get_session)) -> GeneratedReportService:
    """GeneratedReportService 팩토리."""
    return GeneratedReportService.from_session(session)


# ============================================================
# Reference Endpoints
# ============================================================
@router.get("/companies", response_model=list[CompanyResponse])
async def get_companies(service: CompanyService = Depends(get_company_service)) -> list[CompanyResponse]:
    """등록된 전체 기업 목록을 조회한다."""
    companies = await service.get_all_companies(limit=100)
    return [CompanyResponse.model_validate(company) for company in companies]


@router.get("/topics")
async def get_topics() -> list[dict]:
    """분석 주제 목록을 반환한다."""
    return [{"id": t["id"], "label": t["label"]} for t in TOPICS]


@router.get("/company/trending", response_model=list[CompanyResponse])
async def get_trending_companies(service: CompanyService = Depends(get_company_service)) -> list[CompanyResponse]:
    """
    최근 분석된(업데이트된) 기업 최대 9개를 반환한다.

    DB의 companies 테이블에서 updated_at 기준 내림차순으로 조회한다.
    """
    companies = await service.get_all_companies(limit=9, skip=0, order_by="updated_at")
    # updated_at 내림차순 정렬 (서비스 레이어가 ascending=True 기본이므로 역순)
    companies_sorted = sorted(companies, key=lambda c: c.updated_at or c.created_at, reverse=True)
    return [CompanyResponse.model_validate(c) for c in companies_sorted]


@router.get("/company/search", response_model=list[CompanyResponse])
async def search_companies(query: str, service: CompanyService = Depends(get_company_service)) -> list[CompanyResponse]:
    """
    기업명 부분 일치 검색.

    Args:
        query: 검색어 (기업명의 일부)

    Returns:
        매칭된 기업 목록 (최대 10개)
    """
    companies = await service.search_by_name(query)
    return [CompanyResponse.model_validate(c) for c in companies]


@router.get("/reports/company/{company_name}", response_model=list[GeneratedReportListItem])
async def get_reports_by_company(
    company_name: str, service: GeneratedReportService = Depends(get_generated_report_service)
) -> list[GeneratedReportListItem]:
    """
    특정 기업의 모든 생성 리포트를 조회한다.

    Args:
        company_name: 기업명

    Returns:
        해당 기업의 생성 리포트 목록 (최신순)
    """
    reports = await service.get_reports_by_company_name(company_name)
    return [GeneratedReportListItem.model_validate(r) for r in reports]


# ============================================================
# Report Generation
# ============================================================
@router.post("/generate", response_model=ReportJobResponse)
async def request_report_generation(
    request: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    job_service: ReportJobService = Depends(get_report_job_service),
) -> ReportJobResponse:
    """
    STORM 리포트 생성을 요청한다.

    1. DB에 Job 생성 (PENDING)
    2. BackgroundTasks로 파이프라인 위임
    3. job_id 즉시 반환 → 프론트에서 polling
    """
    company_name = request.company_name.strip()
    topic = request.topic.strip()

    try:
        job_id = await storm_service.create_job(company_name=company_name, topic=topic)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Job creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job") from e

    background_tasks.add_task(storm_service.run_pipeline, job_id=job_id, company_name=company_name, topic=topic)

    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=500, detail="Job created but not found in DB")

    return ReportJobResponse.model_validate(job)


# ============================================================
# Job Status (Polling)
# ============================================================
@router.get("/status/{job_id}")
async def get_job_status(job_id: str, job_service: ReportJobService = Depends(get_report_job_service)) -> dict:
    """
    작업 상태를 조회한다.

    1차: 메모리(JOBS)에서 실시간 progress 조회
    2차: 메모리에 없으면 DB 폴백
    """
    mem_status = storm_service.get_job_status_from_memory(job_id)
    if mem_status:
        return {
            "job_id": job_id,
            "status": mem_status["status"],
            "progress": mem_status["progress"],
            "message": mem_status.get("message", ""),
            "report_id": mem_status.get("report_id"),
            "quality_grade": mem_status.get("quality_grade"),
        }

    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    status_str = job.status.value if hasattr(job.status, "value") else str(job.status)
    return {
        "job_id": job.id,
        "status": status_str,
        "progress": 100 if status_str == "COMPLETED" else 0,
        "message": job.error_message or "",
        "report_id": None,
    }


# ============================================================
# Report Retrieval
# ============================================================
@router.get("/report/{report_id}", response_model=GeneratedReportResponse)
async def get_report(
    report_id: int, service: GeneratedReportService = Depends(get_generated_report_service)
) -> GeneratedReportResponse:
    """리포트 PK(int)로 조회한다."""
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return GeneratedReportResponse.model_validate(report)


@router.get("/report/by-job/{job_id}", response_model=GeneratedReportResponse)
async def get_report_by_job_id(
    job_id: str, service: GeneratedReportService = Depends(get_generated_report_service)
) -> GeneratedReportResponse:
    """Job ID(UUID)로 리포트를 조회한다."""
    report = await service.get_report_by_job_id(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return GeneratedReportResponse.model_validate(report)


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    limit: int = 20, offset: int = 0, job_service: ReportJobService = Depends(get_report_job_service)
) -> ReportListResponse:
    """최신 순으로 Job 목록을 조회한다."""
    total, jobs = await job_service.list_jobs(limit=limit, offset=offset)
    summaries = [ReportSummary.model_validate(job) for job in jobs]
    return ReportListResponse(total=total, reports=summaries)
