"""
Enterprise STORM API (FastAPI)

역할:
    - 프론트엔드(React)와 통신하는 HTTP API 계층
    - StormService를 통해 백그라운드 파이프라인 실행/상태 관리
    - Service 계층을 통해 DB 조회 (Controller → Service → Repository)

구조:
    main.py (Controller) → src/services (Service) → src/repositories (Repository)
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.config import TOPICS
from src.common.database.connection import AsyncDatabaseEngine
from src.company.schemas.company import CompanyResponse
from src.company.schemas.generated_report import GeneratedReportResponse, GenerateReportRequest
from src.company.schemas.report_job import ReportJobResponse, ReportListResponse, ReportSummary
from src.company.services.company_service import CompanyService
from src.company.services.generated_report_service import GeneratedReportService
from src.company.services.report_job_service import ReportJobService
from src.company.services.storm_service import StormService


# ============================================================
# Setup
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_engine = AsyncDatabaseEngine()
storm_service = StormService()

app = FastAPI(
    title="Enterprise STORM API",
    description="AI-powered Corporate Report Generation API",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Lifecycle
# ============================================================
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting Enterprise STORM API v4.0...")
    await db_engine.initialize()
    logger.info("✓ Database ready")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down API...")
    await db_engine.dispose()
    try:
        from backend.src.common.services.embedding import Embedding

        embedding = Embedding.get_instance()
        if embedding:
            await embedding.aclose()
    except Exception as e:
        logger.warning(f"Embedding client close skipped: {e}")
    logger.info("✓ Database connections closed")


# ============================================================
# Dependencies (Service Factory — Controller는 Service만 사용)
# ============================================================
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공."""
    async with db_engine.get_session() as session:
        yield session


async def get_company_service(
    session: AsyncSession = Depends(get_session),
) -> CompanyService:
    return CompanyService.from_session(session)


async def get_report_job_service(
    session: AsyncSession = Depends(get_session),
) -> ReportJobService:
    return ReportJobService.from_session(session)


async def get_generated_report_service(
    session: AsyncSession = Depends(get_session),
) -> GeneratedReportService:
    return GeneratedReportService.from_session(session)


# ============================================================
# Health & Reference Endpoints
# ============================================================
@app.get("/")
async def root():
    return {"status": "operational", "version": "4.0.0"}


@app.get("/api/companies", response_model=list[CompanyResponse])
async def get_companies(
    service: CompanyService = Depends(get_company_service),
):
    return await service.get_all_companies(limit=100)


@app.get("/api/topics")
async def get_topics():
    return [{"id": t["id"], "label": t["label"]} for t in TOPICS]


# ============================================================
# Report Generation (핵심 Flow)
# ============================================================
@app.post("/api/generate", response_model=ReportJobResponse)
async def request_report_generation(
    request: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    job_service: ReportJobService = Depends(get_report_job_service),
):
    """
    1. DB에 Job 생성 (PENDING)
    2. BackgroundTasks로 파이프라인 위임
    3. job_id 즉시 반환 → 프론트에서 polling
    """
    company_name = request.company_name.strip()
    topic = request.topic.strip()

    try:
        job_id = await storm_service.create_job(
            company_name=company_name,
            topic=topic,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Job creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job") from e

    # 백그라운드로 파이프라인 실행 등록
    background_tasks.add_task(
        storm_service.run_pipeline,
        job_id=job_id,
        company_name=company_name,
        topic=topic,
    )

    # Service를 통해 Job 조회하여 응답
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=500, detail="Job created but not found in DB")

    return job


# ============================================================
# Job Status (Polling)
# ============================================================
@app.get("/api/status/{job_id}")
async def get_job_status(
    job_id: str,
    job_service: ReportJobService = Depends(get_report_job_service),
):
    """
    1차: 메모리(JOBS)에서 실시간 progress 조회
    2차: 메모리에 없으면 DB 폴백
    """
    # 메모리 조회 (실시간 progress 포함)
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

    # DB 폴백 (서버 재시작 후 등) — Service 계층 사용
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # 프론트엔드 기대 형식에 맞추어 반환 (메모리 응답과 동일 구조)
    status_str = job.status.value if hasattr(job.status, 'value') else str(job.status)
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
@app.get("/api/report/{report_id}", response_model=GeneratedReportResponse)
async def get_report(
    report_id: int,
    service: GeneratedReportService = Depends(get_generated_report_service),
):
    """리포트 PK(int)로 조회"""
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/api/report/by-job/{job_id}", response_model=GeneratedReportResponse)
async def get_report_by_job_id(
    job_id: str,
    service: GeneratedReportService = Depends(get_generated_report_service),
):
    """Job ID(UUID)로 리포트 조회"""
    report = await service.get_report_by_job_id(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/api/reports", response_model=ReportListResponse)
async def list_reports(
    limit: int = 20,
    offset: int = 0,
    job_service: ReportJobService = Depends(get_report_job_service),
):
    """최신 순으로 Job 목록을 조회합니다."""
    total, jobs = await job_service.list_jobs(limit=limit, offset=offset)

    summaries = [ReportSummary.model_validate(job) for job in jobs]

    return ReportListResponse(total=total, reports=summaries)


# ============================================================
# Error Handler
# ============================================================
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "요청한 리소스를 찾을 수 없습니다.",
            "path": str(request.url),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.",
            "detail": str(exc),
        },
    )


# ============================================================
# 서버 실행 가이드
# ============================================================
"""
[실행 방법]
1. 프로젝트 루트 디렉토리로 이동
2. 터미널에서 실행:

   # 개발 모드 (자동 리로드 — 소스 디렉토리만 감시)
   python -m uvicorn main:app --reload --port 8000 --reload-dir backend --reload-dir backend

   # 프로덕션 모드
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

[검증 명령어]
1. Health Check:
   curl http://localhost:8000/

2. 리포트 조회 (핵심):
   curl http://localhost:8000/api/report/1

3. 리포트 생성 요청:
   curl -X POST http://localhost:8000/api/generate \
     -H "Content-Type: application/json" \
     -d '{"company_name": "SK하이닉스", "topic": "재무 분석"}'

4. 작업 상태 조회:
   curl http://localhost:8000/api/status/mock-job-001

5. 리포트 목록:
   curl http://localhost:8000/api/reports

[브라우저 API 문서]
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
"""
