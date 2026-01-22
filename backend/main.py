"""
FastAPI Backend API for Enterprise STORM Frontend Integration (v3.1)
Task ID: PHASE-3-Backend-Integration
Target: Service Layer Integration Fixes & DB Save Reliability

✅ Phase 3.1 Changes:
- Fixed Service method calls (Removed redundant 'session' arguments)
- Removed redundant session context managers in endpoints
- Integrated robust background task execution for DB saving
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

# Background Service
from backend.storm_service import run_storm_pipeline
from src.common.config import (
    JOB_STATUS,
    get_canonical_company_name,
    get_topic_list_for_api,
)

# Service Layer & Database Engine
from src.database import AsyncDatabaseEngine
from src.database.repositories import CompanyRepository, GeneratedReportRepository
from src.services import CompanyService, GenerationService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# FastAPI App Initialization
# ============================================================
app = FastAPI(
    title="Enterprise STORM API",
    description="AI-powered Corporate Report Generation API (v3.1 - Refactored)",
    version="3.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================
# Global State
# ============================================================
JOBS = {}
db_engine = AsyncDatabaseEngine()

# ============================================================
# CORS Middleware
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Pydantic Models
# ============================================================


class GenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"company_name": "SK하이닉스", "topic": "재무 분석"}
        }
    )
    company_name: str
    topic: str = "종합 분석"


class CompanyInfo(BaseModel):
    id: int
    name: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    report_id: int | None = None
    progress: int | None = None
    message: str | None = None


class ReportResponse(BaseModel):
    report_id: int
    company_name: str
    topic: str
    report_content: str
    toc_text: str | None = None
    references: dict[str, Any] | None = None
    meta_info: dict[str, Any] | None = None
    model_name: str | None = "gpt-4o"
    created_at: str | None = None
    status: str = "completed"


class ReportSummary(BaseModel):
    report_id: int
    company_id: int | None = None
    company_name: str
    topic: str
    model_name: str | None
    created_at: str | None
    status: str


class ReportListResponse(BaseModel):
    total: int
    reports: list[ReportSummary]


# ============================================================
# Dependency Injection
# ============================================================


async def get_company_service():
    """Dependency: CompanyService with active session"""
    async with db_engine.get_session() as session:
        repo = CompanyRepository(session)
        service = CompanyService(repo)
        yield service


async def get_generation_service():
    """Dependency: GenerationService with active session"""
    async with db_engine.get_session() as session:
        generated_repo = GeneratedReportRepository(session)
        company_repo = CompanyRepository(session)
        service = GenerationService(generated_repo, company_repo)
        yield service


# ============================================================
# Lifecycle Events
# ============================================================


@app.on_event("startup")
async def startup_event():
    """
    [Modified] DB 엔진 초기화를 명시적으로 호출합니다.
    """
    logger.info("🚀 Starting Enterprise STORM API v3.1...")
    await db_engine.initialize()
    logger.info("✓ AsyncDatabaseEngine initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """
    [Modified] DB 엔진 리소스를 정리합니다.
    """
    logger.info("🛑 Shutting down API...")
    await db_engine.dispose()
    logger.info("✓ Database connections closed")


# ============================================================
# API Endpoints
# ============================================================


@app.get("/")
async def root():
    return {"status": "operational", "version": "3.1.0", "mode": "service-layer-fixed"}


@app.get("/api/companies", response_model=list[CompanyInfo])
async def get_companies(service: CompanyService = Depends(get_company_service)):
    """
    [Modified] Service Layer 호출 시 불필요한 session 인자를 제거했습니다.
    """
    try:
        # service.list_companies()는 session 인자를 받지 않습니다 (Repository가 내부적으로 가지고 있음)
        companies = await service.list_companies(limit=100)
        return [CompanyInfo(id=c.id, name=c.company_name) for c in companies]
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))  # noqa: B904


@app.get("/api/topics")
async def get_topics():
    return get_topic_list_for_api()


@app.post("/api/generate", response_model=JobStatusResponse)
async def generate_report(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    [Modified] storm_service.run_storm_pipeline을 백그라운드 작업으로 등록합니다.
    """
    try:
        company_name = get_canonical_company_name(request.company_name.strip())
        topic = request.topic.strip()
        job_id = f"job-{uuid.uuid4()}"

        JOBS[job_id] = {
            "status": JOB_STATUS.PROCESSING.value,
            "company_name": company_name,
            "topic": topic,
            "progress": 0,
            "created_at": datetime.now().isoformat(),
        }

        # [Refactor] DB 연결을 독립적으로 관리하는 새로운 백그라운드 서비스 사용
        background_tasks.add_task(
            run_storm_pipeline,
            job_id=job_id,
            company_name=company_name,
            topic=topic,
            jobs_dict=JOBS,
        )

        return JobStatusResponse(
            job_id=job_id,
            status=JOB_STATUS.PROCESSING.value,
            progress=0,
            message=f"Starting generation for {company_name}",
        )
    except Exception as e:
        logger.error(f"Generate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job.get("status"),
        report_id=job.get("report_id"),
        progress=job.get("progress", 0),
        message=job.get("message"),
    )


@app.get("/api/report/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int, service: GenerationService = Depends(get_generation_service)
):
    """
    [Modified] Service Layer 호출 시 불필요한 session 인자를 제거했습니다.
    """
    try:
        report = await service.get_report_by_id(report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return ReportResponse(
            report_id=report.id,
            company_name=report.company_name,
            topic=report.topic,
            report_content=report.report_content,
            toc_text=report.toc_text,
            references=report.references_data,
            meta_info=report.meta_info,
            model_name=report.model_name,
            created_at=report.created_at.isoformat() if report.created_at else None,
            status=JOB_STATUS.COMPLETED.value,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports", response_model=ReportListResponse)
async def list_reports(
    company_name: str | None = None,
    topic: str | None = None,
    limit: int = 10,
    offset: int = 0,
    service: GenerationService = Depends(get_generation_service),
):
    """
    [Modified] Service Layer의 list_reports 메서드를 사용하도록 변경했습니다.
    """
    try:
        filters = {}
        if company_name:
            filters["company_name"] = company_name
        if topic:
            filters["topic"] = topic

        # [Refactor] Repository 직접 접근 대신 Service 메서드 사용
        reports = await service.list_reports(
            filters=filters, limit=limit, offset=offset
        )

        # 전체 개수 조회 (Service 메서드 활용)
        total = await service.count_reports(filters=filters)

        summaries = [
            ReportSummary(
                report_id=r.id,
                company_id=r.company_id,
                company_name=r.company_name,
                topic=r.topic,
                model_name=r.model_name,
                created_at=r.created_at.isoformat() if r.created_at else None,
                status=JOB_STATUS.COMPLETED.value,
            )
            for r in reports
        ]

        return ReportListResponse(total=total, reports=summaries)
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Error Handlers
# ============================================================


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "message": "요청한 리소스를 찾을 수 없습니다.",
        "path": str(request.url),
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {
        "error": "Internal Server Error",
        "message": "서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.",
        "detail": str(exc),
    }


# ============================================================
# 서버 실행 가이드
# ============================================================
"""
[실행 방법]
1. 프로젝트 루트 디렉토리로 이동
2. 터미널에서 실행:

   # 개발 모드 (자동 리로드)
   python -m uvicorn backend.main:app --reload --port 8000

   # 프로덕션 모드
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4

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
