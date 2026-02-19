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
from backend.src.common.middlewares.auth import check_admin_permission
from backend.src.company.schemas.company import CompanyResponse
from backend.src.company.schemas.generated_report import (
    GeneratedReportListItem,
    GeneratedReportResponse,
    GenerateReportRequest,
)
from backend.src.company.schemas.report_job import (
    AdminAnalysisRequestResponse,
    AdminAnalysisRequestsResponse,
    AdminApproveRequest,
    AdminRejectRequest,
    CompanyAnalysisRequestCreate,
    CompanyAnalysisRequestResponse,
    ReportJobResponse,
    ReportListResponse,
    ReportSummary,
)
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


# ============================================================
# 기업 분석 요청 플로우 (구직자 <-> 관리자)
# ============================================================
@router.post("/company/analyze/request", response_model=CompanyAnalysisRequestResponse, status_code=201)
async def submit_analysis_request(
    request: CompanyAnalysisRequestCreate, user_id: int, job_service: ReportJobService = Depends(get_report_job_service)
) -> CompanyAnalysisRequestResponse:
    """
    구직자가 기업 분석을 요청합니다.

    Happy Path:
    - 사용자가 로그인 상태에서 분석 요청
    - 중복 요청 여부 확인 후 PENDING 상태로 저장
    - job_id 반환

    Edge Cases:
    - user_id가 없으면 401 Unauthorized
    - 동일 기업에 대한 미완료 요청이 있으면 400 Bad Request
    """
    from backend.src.common.repositories.base_repository import EntityNotFound

    try:
        job_id = await job_service.submit_analysis_request(
            user_id=user_id, company_id=request.company_id, company_name=request.company_name, topic=request.topic
        )
    except EntityNotFound as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=500, detail="Job created but not found in DB")

    return CompanyAnalysisRequestResponse.model_validate(job)


@router.get("/company/analyze/requests", response_model=list[CompanyAnalysisRequestResponse])
async def get_user_analysis_requests(
    user_id: int, job_service: ReportJobService = Depends(get_report_job_service)
) -> list[CompanyAnalysisRequestResponse]:
    """
    구직자의 모든 분석 요청을 조회합니다.

    요청 상태를 확인하여 대기 / 진행 / 완료 / 반려 중 어느 상태인지 확인할 수 있습니다.

    Args:
        user_id: 사용자의 ID (JWT 토큰에서 추출)

    Returns:
        사용자가 요청한 모든 분석 요청 목록 (최신순)
    """
    jobs = await job_service.get_user_requests(user_id)
    return [CompanyAnalysisRequestResponse.model_validate(job) for job in jobs]


@router.get("/admin/analyze/requests", response_model=AdminAnalysisRequestsResponse)
async def get_pending_analysis_requests(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> AdminAnalysisRequestsResponse:
    """
    관리자: 승인 대기 중인 모든 분석 요청을 조회합니다.

    관리자만 접근 가능합니다. 권한 검증은 백엔드에서 엄격히 처리됩니다.

    Args:
        user_id: 관리자의 ID (권한 검증용)

    Returns:
        승인 대기 중인 요청 목록 (먼저 요청된 순)

    Raises:
        403 Forbidden: 관리자 권한이 없을 경우
    """
    # 관리자 권한 검증
    await check_admin_permission(user_id, session)

    jobs = await job_service.get_pending_requests()
    total = len(jobs)
    requests_list = [AdminAnalysisRequestResponse.model_validate(job) for job in jobs]
    return AdminAnalysisRequestsResponse(total=total, requests=requests_list)


@router.post("/admin/analyze/{job_id}/approve", status_code=204)
async def approve_analysis_request(
    job_id: str,
    request: AdminApproveRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> None:
    """
    관리자가 분석 요청을 승인합니다.

    관리자만 접근 가능합니다. 승인 후 PROCESSING 상태로 변경되고 백그라운드에서 분석이 시작됩니다.

    Args:
        job_id: 승인할 요청 ID
        request: 승인 정보 (관리자 ID)

    Raises:
        403 Forbidden: 관리자 권한이 없을 경우
        404 Not Found: 요청이 없거나 이미 처리된 경우
    """
    # 관리자 권한 검증
    await check_admin_permission(request.approved_by_user_id, session)

    from backend.src.common.repositories.base_repository import EntityNotFound

    try:
        await job_service.approve_request(job_id, request.approved_by_user_id)
        # 리포트 생성 파이프라인 트리거
        # 기존 report_jobs 처리 로직과 통합
        job = await job_service.get_job(job_id)
        if job:
            background_tasks.add_task(
                storm_service.run_pipeline, job_id=job_id, company_name=job.company_name, topic=job.topic
            )
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/admin/analyze/{job_id}/reject", status_code=204)
async def reject_analysis_request(
    job_id: str,
    request: AdminRejectRequest,
    session: AsyncSession = Depends(get_session),
    job_service: ReportJobService = Depends(get_report_job_service),
) -> None:
    """
    관리자가 분석 요청을 반려합니다.

    관리자만 접근 가능합니다. 반려 후 REJECTED 상태로 변경되고 반려 사유가 저장됩니다.
    구직자는 반려 사유를 확인할 수 있습니다.

    Args:
        job_id: 반려할 요청 ID
        request: 반려 정보 (관리자 ID, 사유)

    Raises:
        403 Forbidden: 관리자 권한이 없을 경우
        404 Not Found: 요청이 없거나 이미 처리된 경우
    """
    # 관리자 권한 검증
    await check_admin_permission(request.approved_by_user_id, session)

    from backend.src.common.repositories.base_repository import EntityNotFound

    try:
        await job_service.reject_request(job_id, request.approved_by_user_id, request.rejection_reason)
    except EntityNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
