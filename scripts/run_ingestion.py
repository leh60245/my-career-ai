import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

from backend.src.common.database import AsyncDatabaseEngine
from backend.src.common.services.embedding import Embedding
from backend.src.company.repositories.analysis_report_repository import AnalysisReportRepository
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.source_material_repository import SourceMaterialRepository
from backend.src.company.services.analysis_service import AnalysisService
from backend.src.company.services.company_service import CompanyService
from backend.src.company.services.dart_service import DartService
from backend.src.company.services.ingestion_service import IngestionService


# 프로젝트 루트 경로 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("IngestionRunner")


async def process_corp_pipeline(
    session,
    corp_code: str,
    dart_svc: DartService,
    ingest_svc: IngestionService,
    comp_svc: CompanyService,
    anal_svc: AnalysisService,
) -> bool:
    """
    [단일 기업(corp_code) 처리 파이프라인]
    """
    try:
        # 1. DART에서 최신 기업 정보 조회 (Live Data)
        corp_info = dart_svc.get_corp_by_code(corp_code)
        if not corp_info:
            logger.warning(f"   [WARNING] Invalid corp_code: {corp_code} (Not found in DART list)")
            return False

        dart_info = dart_svc.extract_company_info(corp_info)

        company_name = getattr(corp_info, "corp_name", "Unknown")

        logger.info(f"▶️ Start Processing: {company_name} ({corp_code})")

        # 2. Company Onboarding (DB 등록/확인)
        company = await comp_svc.onboard_company(
            corp_code=dart_info["corp_code"],
            company_name=dart_info["company_name"],
            stock_code=dart_info["stock_code"],
            sector=dart_info["sector"],  # 전달
            product=dart_info["product"],  # 전달
        )

        # 3. Fetch Report (최신 사업보고서 조회)
        report = dart_svc.get_annual_report(corp_code=corp_code)
        if not report:
            logger.info(f"   ℹ️ No annual report found for {company_name}")
            return False

        # 4. Save Report Metadata (중복 체크 포함)
        meta_data = dart_svc.extract_report_metadata(report, corp_info)

        # 이미 DB에 해당 접수번호(rcept_no)의 보고서가 있다면 -> Skip or Get Existing
        analysis_report = await anal_svc.save_report_metadata(
            company_id=company.id, data=meta_data, return_existing=True
        )

        # 5. Parse & Ingest Report Sections to Source Material
        raw_chunks = dart_svc.parse_report_sections(report)
        if not raw_chunks:
            logger.warning(f"   [WARNING] No valid sections parsed for {company_name}")
            return False

        saved_chunks = await ingest_svc.save_chunks(analysis_report.id, raw_chunks)

        logger.info(f"    Success: Ingested {len(saved_chunks)} chunks for {company_name}")
        return True

    except Exception as e:
        logger.error(f"   ❌ Failed processing {corp_code}: {str(e)}", exc_info=False)
        # 개별 기업 실패는 전체 파이프라인을 멈추지 않음 (로그 남기고 False 반환)
        return False


async def run_pipeline(
    target_corps: list[str] | None = None,
    helper_stocks: list[str] | None = None,
    days: int = 90,
    limit: int | None = None,
):
    """
    [메인 실행 루프]
    - target_corps가 있으면 그것만 실행 (Manual Mode)
    - 없으면 최근 N일간 보고서를 낸 기업 자동 검색 (Auto/Efficient Mode)
    """

    # 1. 인프라 초기화
    db_engine = AsyncDatabaseEngine()
    embedding = Embedding()
    dart_svc = DartService()

    logger.info("🚀 Initializing Ingestion Pipeline...")

    # 2. 타겟 리스트 확정 (Target Resolution)
    final_targets: list[str] = []  # List of corp_codes

    # [Case A] 명시적 corp_code 지정
    if target_corps:
        logger.info(f"📋 Mode: Manual (Explicit Corp Codes: {len(target_corps)})")
        final_targets.extend(target_corps)

    # [Case B] 편의성 stock_code 지정 (Helper) -> corp_code로 변환
    if helper_stocks:
        logger.info(f"📋 Mode: Helper (Converting {len(helper_stocks)} stock codes...)")
        for stock in helper_stocks:
            corp = dart_svc.get_corp_by_stock_code(stock)
            if corp:
                final_targets.append(corp.corp_code)
            else:
                logger.warning(f"   [WARNING] Stock code not found: {stock}")

    # [Case C] 아무것도 지정 안 함 -> 최근 보고서 제출 기업 자동 검색 (Default)
    if not final_targets:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        logger.info(f"📋 Mode: Auto/Efficient (Reports since {start_date})")

        # DartService에서 "최근 보고서가 있는 기업들의 corp_code"를 가져옴
        # get_corps_with_reports는 (corp_obj) 리스트를 반환한다고 가정
        active_corps = dart_svc.get_corps_with_reports(bgn_de=start_date)

        final_targets = [c.corp_code for c in active_corps if hasattr(c, "corp_code")]
        logger.info(f"   Found {len(final_targets)} companies with recent reports.")

    # 중복 제거 (set)
    final_targets = list(set(final_targets))

    # Limit 적용
    if limit and len(final_targets) > limit:
        logger.info(f"   Refining targets to first {limit} entries.")
        final_targets = final_targets[:limit]

    if not final_targets:
        logger.info("🛑 No targets found. Exiting.")
        return

    # 3. 파이프라인 실행
    stats = {"success": 0, "failed": 0, "skipped": 0}

    async with db_engine.get_session() as session:
        # Service Assembly (Dependency Injection)
        repo_material = SourceMaterialRepository(session)
        repo_company = CompanyRepository(session)
        repo_analysis = AnalysisReportRepository(session)

        ingest_svc = IngestionService(repo_material, embedding)
        comp_svc = CompanyService(repo_company)
        anal_svc = AnalysisService(repo_analysis, repo_company)

        logger.info(f"🚀 Starting Batch for {len(final_targets)} companies...\n")

        for idx, corp_code in enumerate(final_targets):
            print(f"[{idx + 1}/{len(final_targets)}] Processing CorpCode: {corp_code}...")

            try:
                # 기업 단위 트랜잭션 격리
                async with session.begin_nested():
                    success = await process_corp_pipeline(session, corp_code, dart_svc, ingest_svc, comp_svc, anal_svc)

                    if success:
                        stats["success"] += 1
                    else:
                        stats["skipped"] += 1  # 실패가 아니라, 보고서가 없거나 이미 있어서 넘어간 경우 등

                await session.commit()

            except Exception as e:
                # 여기서 잡히는 건 process_corp_pipeline 내부에서 처리되지 않은 심각한 에러
                logger.error(f"🔥 Critical Error on {corp_code}: {e}")
                stats["failed"] += 1
                # 메인 루프 계속 진행

    # 4. 종료
    await db_engine.dispose()

    print("\n" + "=" * 50)
    print("📊 Ingestion Summary")
    print(f"   Total Targets: {len(final_targets)}")
    print(f"   Success: {stats['success']}")
    print(f"   Skipped/No Report: {stats['skipped']}")
    print(f"   Failed : {stats['failed']}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DART Report Ingestion Pipeline")

    # Args 구조 변경
    parser.add_argument("--corps", nargs="+", help="Target specific Corp Codes (e.g., 00126380)")
    parser.add_argument("--stocks", nargs="+", help="Target specific Stock Codes (Helper, converted to Corp Code)")
    parser.add_argument("--days", type=int, default=90, help="Lookback days for Auto Mode (default: 90)")
    parser.add_argument("--limit", type=int, help="Max number of companies to process")

    args = parser.parse_args()

    try:
        asyncio.run(run_pipeline(target_corps=args.corps, helper_stocks=args.stocks, days=args.days, limit=args.limit))
    except KeyboardInterrupt:
        logger.info("🛑 Pipeline stopped by user.")
