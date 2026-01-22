#!/usr/bin/env python
"""
데이터 수집 파이프라인 실행 스크립트 (run_ingestion_v3.py)

PHASE 3.5: Legacy Migration Complete
- Refactored to call Async methods directly (No nested asyncio.run)
- Implements DB Reset using AsyncDatabaseEngine
- Orchestrates DART Agent -> DataPipeline -> EmbeddingWorker
"""

import argparse
import asyncio
import logging
import os
import sys

from sqlalchemy import func, select

# NEW: Service Layer & Database Engine
# 여기에 # noqa: E402를 붙여서 경고를 무시합니다.
from src.database import AsyncDatabaseEngine
from src.database.models import Base
from src.database.repositories import (
    AnalysisReportRepository,
    CompanyRepository,
    SourceMaterialRepository,
)

# Refactored Modules
from src.ingestion.embedding_worker import ContextLookbackEmbeddingWorker  # noqa: E402
from src.ingestion.pipeline import DataPipeline  # noqa: E402

# 프로젝트 루트를 path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# Helper Functions
# ============================================================


async def reset_database():
    """DB 초기화: 모든 테이블 삭제 후 재생성"""
    logger.warning("⚠️ RESETTING DATABASE: All data will be lost!")

    db_engine = AsyncDatabaseEngine()
    await db_engine.initialize()

    async with db_engine.engine.begin() as conn:
        # 의존성 순서에 따라 Drop (반대 순서 아님, cascade가 없으면 순서 중요)
        # Base.metadata.drop_all은 순서를 알아서 처리함
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("✅ All tables dropped.")

        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ All tables recreated.")

    await db_engine.dispose()


# ============================================================
# Async Execution Functions
# ============================================================


async def run_efficient_mode_async(
    reset_db: bool = False,
    limit: int | None = None,
    bgn_de: str | None = None,
    end_de: str | None = None,
):
    """
    효율 모드: 최근 사업보고서가 있는 기업만 선별하여 수집합니다.
    """
    if reset_db:
        await reset_database()

    logger.info("🔄 Efficient Mode: Searching for targets...")

    pipeline = DataPipeline()

    # 1. 대상 기업 검색 (Sync Agent call - It's okay in script level)
    # pipeline.run_efficient()는 내부에서 asyncio.run을 쓰므로 사용 금지
    # 직접 Agent를 통해 타겟을 가져옵니다.
    corps_with_reports = pipeline.agent.get_corps_with_reports(
        bgn_de=bgn_de, end_de=end_de
    )

    if limit:
        corps_with_reports = corps_with_reports[:limit]

    # (Corp, Report) 튜플에서 Corp 객체만 추출
    targets = [item[0] for item in corps_with_reports]

    logger.info(f"📋 Found {len(targets)} targets with reports.")

    # 2. Async 파이프라인 실행
    await pipeline.run_pipeline_async(targets)

    logger.info("✅ Efficient mode complete")


async def run_custom_mode_async(stock_codes: list, reset_db: bool = False):
    """
    커스텀 모드: 지정한 종목코드 리스트에 대해서만 수집을 수행합니다.
    """
    if reset_db:
        await reset_database()

    logger.info(f"🔄 Custom Mode: Processing stock codes: {stock_codes}")

    pipeline = DataPipeline()

    # 1. 종목코드로 Corp 객체 변환
    targets = []
    for code in stock_codes:
        corp = pipeline.agent.get_corp_by_stock_code(code)
        if corp:
            targets.append(corp)
        else:
            logger.warning(f"⚠️ Stock code not found: {code}")

    if not targets:
        logger.error("❌ No valid targets found.")
        return

    # 2. Async 파이프라인 실행
    await pipeline.run_pipeline_async(targets)

    logger.info("✅ Custom mode complete")


async def run_embed_mode_async(
    batch_size: int = 32, limit: int | None = None, force: bool = False
):
    """
    임베딩 생성 모드: 수집된 텍스트 데이터에 대해 벡터 임베딩을 생성합니다.
    """
    logger.info("🔄 Embedding Mode: Generating embeddings with context look-back...")

    worker = ContextLookbackEmbeddingWorker(batch_size=batch_size)

    # Async Run 호출
    await worker.run_async(limit=limit, force=force)

    logger.info("✅ Embedding mode complete")


async def run_stats_mode_async():
    """
    DB 통계 조회: 현재 데이터베이스의 적재 현황을 보여줍니다.
    """
    logger.info("\n[STATS] DB Statistics")
    logger.info("=" * 40)

    db_engine = AsyncDatabaseEngine()

    async with db_engine.get_session() as session:
        company_repo = CompanyRepository(session)
        analysis_repo = AnalysisReportRepository(session)
        source_repo = SourceMaterialRepository(session)

        # 1. 기본 레코드 카운트
        companies_count = (await company_repo.count()) or 0
        reports_count = (await analysis_repo.count()) or 0

        # Source Material 전체 카운트
        # repo.count()는 필터 없이 전체 개수
        materials_count = (await source_repo.count()) or 0

        # 2. 임베딩 완료된 청크 카운트
        # ORM으로 카운트 조회
        stmt = select(func.count(source_repo.model.id)).where(
            source_repo.model.embedding.is_not(None)
        )
        result = await session.execute(stmt)
        embedded_count = result.scalar() or 0

        # 3. 결과 출력
        logger.info(f"   Companies       : {companies_count:,}")
        logger.info(f"   Reports         : {reports_count:,}")
        logger.info(f"   Source Materials: {materials_count:,}")
        logger.info(f"   Embedded chunks : {embedded_count:,}")

        if materials_count > 0:
            embed_rate = (embedded_count / materials_count) * 100
            logger.info(f"   Embedding Rate  : {embed_rate:.1f}%")
        else:
            logger.info("   Embedding Rate  : 0.0% (No materials)")

    await db_engine.dispose()
    logger.info("=" * 40)


# ============================================================
# Main Entry Point
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Enterprise STORM Data Ingestion Pipeline (v3.5 Async)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Efficient mode (companies with reports)
    python -m scripts.run_ingestion_v3 --efficient
    
    # Specific companies
    python -m scripts.run_ingestion_v3 --codes 005930,000660
    
    # Generate embeddings
    python -m scripts.run_ingestion_v3 --embed --batch-size 64
    
    # DB statistics
    python -m scripts.run_ingestion_v3 --stats
""",
    )

    # 실행 모드
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--efficient",
        action="store_true",
        help="Efficient mode (companies with reports)",
    )
    mode_group.add_argument("--codes", type=str, help="Stock codes (comma separated)")
    mode_group.add_argument(
        "--embed", action="store_true", help="Embedding generation mode"
    )
    mode_group.add_argument("--stats", action="store_true", help="DB statistics")

    # 공통 옵션
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Reset DB before execution (WARNING: Deletes all data)",
    )
    parser.add_argument("--limit", type=int, help="Max companies/items to process")
    parser.add_argument("--bgn-de", type=str, help="Search start date (YYYYMMDD)")
    parser.add_argument("--end-de", type=str, help="Search end date (YYYYMMDD)")

    # 임베딩 옵션
    parser.add_argument(
        "--batch-size", type=int, default=32, help="Embedding batch size"
    )
    parser.add_argument(
        "--force", action="store_true", help="Regenerate existing embeddings"
    )

    args = parser.parse_args()

    # Asyncio 실행 래퍼
    if args.efficient:
        asyncio.run(
            run_efficient_mode_async(
                reset_db=args.reset_db,
                limit=args.limit,
                bgn_de=args.bgn_de,
                end_de=args.end_de,
            )
        )
    elif args.codes:
        stock_codes = [code.strip() for code in args.codes.split(",")]
        asyncio.run(run_custom_mode_async(stock_codes, reset_db=args.reset_db))
    elif args.embed:
        asyncio.run(
            run_embed_mode_async(
                batch_size=args.batch_size, limit=args.limit, force=args.force
            )
        )
    elif args.stats:
        asyncio.run(run_stats_mode_async())


if __name__ == "__main__":
    main()
