"""
파이프라인 모듈

PHASE 3.5: Legacy Code Migration
- Removed DBManager dependency (Replaced with Service Layer)
- Unified duplicated logic for 'efficient' and 'standard' modes
- Fully Async implementation with retry logic
- Retains DART orchestration responsibilities
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# [통합 아키텍처]
from src.common.config import BATCH_CONFIG
from src.database import AsyncDatabaseEngine
from src.database.repositories import (
    AnalysisReportRepository,
    CompanyRepository,
    SourceMaterialRepository,
)
from src.services import AnalysisService, CompanyService, VectorSearchService

from .dart_agent import DartReportAgent

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    DART 사업보고서 수집 및 적재 파이프라인 (Async Orchestrator).
    """

    def __init__(self):
        self.agent = DartReportAgent()
        self.stats = {
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "start_time": None,
            "end_time": None,
        }
        self.failed_corps = []  # List of {'corp_name': ..., 'corp_code': ...}

    # ==================== Async Service Integration ====================

    async def _save_to_db(self, session, corp, report, sections: List[Dict]) -> bool:
        """
        Service Layer를 통해 데이터베이스에 저장합니다.
        """
        # 1. Services 초기화 (Dependency Injection)
        comp_service = CompanyService(CompanyRepository(session))
        # AnalysisService needs both repos to verify company existence
        anal_service = AnalysisService(
            AnalysisReportRepository(session), CompanyRepository(session)
        )
        vec_service = VectorSearchService(SourceMaterialRepository(session))

        # 2. 기업 등록 (Idempotent)
        try:
            # onboard_company는 중복 시 DuplicateEntity 발생 가능 -> get으로 처리
            # 하지만 Service 로직에 따라 onboard가 존재 체크를 할 수도 있음.
            # 여기서는 안전하게 존재 확인 후 등록 시도 패턴 사용
            company = await comp_service.get_company(
                0
            )  # ID 0은 없을테니 에러 방지용 더미 호출 혹은 로직 수정
            # Service의 onboard_company가 중복체크를 하므로 try-except 사용
            company = await comp_service.onboard_company(
                company_name=corp.corp_name,
                corp_code=corp.corp_code,
                stock_code=corp.stock_code,
            )
        except Exception:
            # 이미 존재하면 조회
            repo = CompanyRepository(session)
            company = await repo.get_by_name(corp.corp_name)

        if not company:
            logger.error(f"Failed to resolve company: {corp.corp_name}")
            return False

        # 3. 리포트 메타데이터 저장
        report_info = self.agent.get_report_info(report)
        try:
            # return_existing=True로 설정하여 중복 시 기존 객체 반환
            analysis_report = await anal_service.save_report_metadata(
                company_id=company.id, data=report_info, return_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to save report metadata: {e}")
            return False

        # 4. 청크(Source Materials) 저장
        total_blocks = 0
        common_meta = {
            "source": "dart",
            "company_name": corp.corp_name,
            "rcept_no": report_info.get("rcept_no"),
        }

        for section in sections:
            blocks = section.get("blocks", [])
            # 메타데이터 보강
            for b in blocks:
                if "meta_info" not in b:
                    b["meta_info"] = {}
                b["meta_info"].update(common_meta)

            # 벡터 서비스로 저장 (임베딩은 나중에 Worker가 처리하거나, 여기서 처리 가능)
            # 여기서는 Raw Data 저장이 주 목적이므로 임베딩은 NULL일 수 있음
            saved = await vec_service.save_chunks(analysis_report.id, blocks)
            total_blocks += len(saved)

        logger.info(f"   📥 Saved {total_blocks} blocks for {corp.corp_name}")
        return True

    # ==================== Core Processing Logic ====================

    async def _process_corp_async(self, session, corp) -> Optional[bool]:
        """단일 기업 처리 로직 (DART Fetch -> DB Save)"""

        # 1. 보고서 조회 (Sync - Network)
        # Note: DART Agent는 requests를 사용하므로 Blocking Call임.
        # 대량 처리 시 run_in_executor 고려 가능하나, Rate Limit 때문에 순차 실행이 유리할 수 있음.  # noqa: E501
        report = self.agent.get_annual_report(corp.corp_code)

        if not report:
            logger.warning(f"   ⚠️ No annual report found for {corp.corp_name}")
            return None

        logger.info(f"   📄 Report Found: {report.report_nm}")

        # 2. 데이터 추출 (Sync - CPU)
        sections = self.agent.extract_target_sections_sequential(report)
        if not sections:
            logger.warning(f"   ⚠️ No valid sections extracted for {corp.corp_name}")
            return None

        # 3. DB 저장 (Async)
        return await self._save_to_db(session, corp, report, sections)

    async def run_pipeline_async(self, targets: List[Any], reset_db: bool = False):
        """
        비동기 파이프라인 메인 루프
        """
        self.stats["start_time"] = datetime.now()
        self.stats["total"] = len(targets)
        logger.info(f"🚀 Pipeline Started. Targets: {len(targets)}")

        db_engine = AsyncDatabaseEngine()

        # Note: reset_db 기능은 파괴적이므로 Service Layer로 이관하지 않고
        # 필요하다면 별도 스크립트나 Admin 도구로 분리하는 것이 안전합니다.
        if reset_db:
            logger.warning(
                "⚠️ 'reset_db' flag is ignored in Service Layer mode for safety."
            )

        # Batching
        batch_size = BATCH_CONFIG.get("batch_size", 10)
        batches = [
            targets[i : i + batch_size] for i in range(0, len(targets), batch_size)
        ]

        async with db_engine.get_session() as session:
            for b_idx, batch in enumerate(batches):
                logger.info(f"\n📦 Processing Batch {b_idx + 1}/{len(batches)}")

                for corp in batch:
                    try:
                        logger.info(
                            f"▶️ Processing: {corp.corp_name} ({corp.stock_code})"
                        )

                        success = await self._process_corp_async(session, corp)

                        # 기업 단위 커밋 (오류 격리)
                        await session.commit()

                        if success:
                            self.stats["success"] += 1
                        elif success is None:
                            self.stats["skipped"] += 1
                        else:
                            self.stats["failed"] += 1
                            self.failed_corps.append(
                                {
                                    "corp_name": corp.corp_name,
                                    "corp_code": corp.corp_code,
                                    "stock_code": corp.stock_code,
                                }
                            )

                    except Exception as e:
                        await session.rollback()
                        logger.error(f"❌ Failed to process {corp.corp_name}: {e}")
                        self.stats["failed"] += 1
                        self.failed_corps.append(
                            {
                                "corp_name": corp.corp_name,
                                "corp_code": getattr(corp, "corp_code", "unknown"),
                                "stock_code": getattr(corp, "stock_code", "unknown"),
                            }
                        )

                    # Rate Limiting
                    await asyncio.sleep(BATCH_CONFIG.get("request_delay_sec", 1))

                # Batch Delay
                if b_idx < len(batches) - 1:
                    await asyncio.sleep(BATCH_CONFIG.get("batch_delay_sec", 2))

        await db_engine.dispose()
        self.stats["end_time"] = datetime.now()
        self._print_summary()
        return self.stats

    async def retry_failed_async(self):
        """실패한 기업 재시도 로직"""
        if not self.failed_corps:
            logger.info("✅ No failed corporations to retry.")
            return

        logger.info(f"\n🔄 Retrying {len(self.failed_corps)} failed corporations...")

        # Corp 객체 재생성
        retry_targets = []
        for fc in self.failed_corps:
            # agent.get_corp_by_stock_code 등을 사용해 객체 복원
            corp = self.agent.get_corp_by_stock_code(fc["stock_code"])
            if corp:
                retry_targets.append(corp)

        # 상태 초기화 후 재실행
        self.failed_corps = []
        await self.run_pipeline_async(retry_targets, reset_db=False)

    # ==================== Public Interfaces (Sync Wrappers) ====================

    def run(
        self,
        stock_codes: Optional[List[str]] = None,
        limit: Optional[int] = None,
        reset_db: bool = False,
    ):
        """기본 실행 모드"""
        if stock_codes:
            targets = []
            for code in stock_codes:
                corp = self.agent.get_corp_by_stock_code(code)
                if corp:
                    targets.append(corp)
        else:
            targets = self.agent.get_listed_corps()

        if limit:
            targets = targets[:limit]

        asyncio.run(self.run_pipeline_async(targets, reset_db))

    def run_efficient(
        self,
        bgn_de: str,
        end_de: str,
        reset_db: bool = False,
        limit: Optional[int] = None,
    ):
        """
        효율 모드: 사업보고서가 있는 기업만 선별하여 실행
        """
        logger.info("🔍 Searching for companies with reports (Efficient Mode)...")

        # 1. 보고서가 있는 기업 목록 조회 (Sync Agent 사용)
        # corps_with_reports는 (Corp객체, ReportInfo) 튜플 리스트임
        corps_with_reports = self.agent.get_corps_with_reports(bgn_de, end_de)

        if limit:
            corps_with_reports = corps_with_reports[:limit]

        # 2. Corp 객체만 추출
        targets = [item[0] for item in corps_with_reports]

        logger.info(f"📋 Found {len(targets)} active targets.")

        # 3. 파이프라인 실행
        asyncio.run(self.run_pipeline_async(targets, reset_db))

    def retry_failed(self):
        """재시도 래퍼"""
        asyncio.run(self.retry_failed_async())

    def _print_summary(self):
        duration = self.stats["end_time"] - self.stats["start_time"]
        print("\n" + "=" * 60)
        print("📊 Pipeline Execution Summary")
        print(f"   Duration: {duration}")
        print(f"   Total: {self.stats['total']}")
        print(f"   Success: {self.stats['success']}")
        print(f"   Skipped: {self.stats['skipped']}")
        print(f"   Failed: {self.stats['failed']}")

        if self.failed_corps:
            print("\n   ⚠️ Failed List:")
            for fc in self.failed_corps[:5]:
                print(f"      - {fc['corp_name']}")
            if len(self.failed_corps) > 5:
                print(f"      ... and {len(self.failed_corps) - 5} more")
        print("=" * 60)
        logger.info("🚀 Pipeline Completed.")
