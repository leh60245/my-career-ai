"""
My Career AI — FastAPI Application Entry Point

역할:
    - FastAPI 앱 선언, CORS 설정, 라이프사이클 관리
    - 각 도메인 라우터를 include_router로 등록
    - 비즈니스 로직은 각 도메인의 Service 계층에 격리
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.company.router import router as company_router
from backend.src.resume.router import router as resume_router
from backend.src.user.router import router as user_router


# ============================================================
# Setup
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_engine = AsyncDatabaseEngine()

app = FastAPI(
    title="My Career AI API",
    description="AI 기반 취업 의사결정 및 코칭 서비스 API",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


# ============================================================
# Lifecycle
# ============================================================
@app.on_event("startup")
async def startup_event() -> None:
    """애플리케이션 시작 시 DB 커넥션 풀 워밍업 및 중단된 잡 복구."""
    logger.info("Starting My Career AI API v5.0...")
    await db_engine.initialize()
    logger.info("Database ready")

    # 서버 재시작 전 PROCESSING 상태로 남아있던 중단된 잡을 FAILED 처리
    try:
        from sqlalchemy.ext.asyncio import AsyncSession

        from backend.src.company.services.report_job_service import ReportJobService

        async with AsyncSession(db_engine.engine) as session:
            recovered = await ReportJobService.from_session(session).recover_interrupted_jobs()
            if recovered:
                logger.warning("서버 재시작: %d개의 중단된 PROCESSING 잡을 FAILED로 복구했습니다.", recovered)
            else:
                logger.info("서버 재시작: 복구가 필요한 중단된 잡 없음.")
    except Exception as e:
        logger.warning("중단된 잡 복구 중 오류 (서버 시작은 계속): %s", e)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """애플리케이션 종료 시 리소스 정리."""
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
# Routers
# ============================================================
app.include_router(company_router)
app.include_router(resume_router)
app.include_router(user_router)


# ============================================================
# Health Check
# ============================================================
@app.get("/")
async def root() -> dict:
    """서버 상태 확인용 헬스체크 엔드포인트."""
    return {"status": "operational", "version": "5.0.0"}


# ============================================================
# Global Error Handlers
# ============================================================
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "message": "요청한 리소스를 찾을 수 없습니다.", "path": str(request.url)},
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
