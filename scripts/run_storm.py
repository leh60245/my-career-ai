#!/usr/bin/env python
"""
Enterprise STORM CLI - 기업 분석 리포트 생성기 (v4.0 - Pipeline Integrated)

Role:
    - 사용자 입력을 받는 CLI 진입점 (Entry Point)
    - ReportJob 생성 (PENDING)
    - src.engine.storm_pipeline 실행 (Orchestrator 호출)

Changes:
    - 모든 비즈니스 로직 제거 -> src/engine/storm_pipeline.py로 위임
    - DB 연결 및 Job 생성 로직 -> src/services/report_job_service.py 사용
    - Thin Client 구조로 변경

Usage:
    python scripts/run_storm.py
    python scripts/run_storm.py --company "삼성전자" --topic "AI 반도체 전망"
"""

import asyncio
import logging
import os
import sys
from argparse import ArgumentParser

from backend.src.common.config import AI_CONFIG, TOPICS
from backend.src.common.database.connection import AsyncDatabaseEngine, ensure_schema
from backend.src.common.enums import ReportJobStatus
from backend.src.company.engine.storm_pipeline import run_storm_pipeline
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.report_job_repository import ReportJobRepository
from backend.src.company.services.report_job_service import ReportJobService


# 프로젝트 루트 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)


async def get_active_companies() -> list[tuple[int, str]]:
    """DB에서 활성화된 기업 목록을 가져옵니다."""
    db = AsyncDatabaseEngine()
    async with db.get_session() as session:
        repo = CompanyRepository(session)
        # 모든 기업을 가져오는 메서드 사용 (없으면 기본 get_all 사용)
        companies = await repo.get_all(limit=100, order_by="company_name")
        return [(c.id, c.company_name) for c in companies]


async def select_company_and_topic_interactive() -> tuple[int, str, str]:
    """
    CLI 인터랙티브 모드: 기업 및 주제 선택
    """
    # 1. 기업 선택
    companies = await get_active_companies()
    if not companies:
        logger.error("❌ DB에 등록된 기업이 없습니다. 'scripts/run_ingestion.py'를 먼저 실행하세요.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("        [ Enterprise STORM 분석기 ]")
    print("=" * 50)
    print("\n🏢 분석할 기업을 선택하세요:")

    for idx, (cid, cname) in enumerate(companies):
        print(f"  [{cid}] {cname}")

    target_company = None
    while not target_company:
        try:
            sel = input("\n👉 기업 ID 입력 (숫자): ").strip()
            sel_id = int(sel)
            target_company = next((item for item in companies if item[0] == sel_id), None)
            if not target_company:
                print("[WARNING] 목록에 없는 ID입니다.")
        except ValueError:
            print("[WARNING] 숫자를 입력해주세요.")

    # 2. 주제 선택
    print(f"\n📝 [{target_company[1]}] 관련 분석 주제를 선택하세요:")
    for idx, topic_obj in enumerate(TOPICS):
        print(f"  [{idx + 1}] {topic_obj['label']}")

    # 마지막 옵션으로 '자유 주제' 추가
    print(f"  [{len(TOPICS) + 1}] (직접 입력)")

    target_topic = ""
    while not target_topic:
        try:
            sel = input("\n👉 주제 번호 입력: ").strip()
            idx = int(sel) - 1

            if 0 <= idx < len(TOPICS):
                target_topic = TOPICS[idx]["label"]
            elif idx == len(TOPICS):
                target_topic = input("   ✍️  질문할 내용을 입력하세요: ").strip()
            else:
                print("[WARNING] 올바른 번호를 입력해주세요.")
        except ValueError:
            print("[WARNING] 숫자를 입력해주세요.")

    return target_company[0], target_company[1], target_topic


async def main():
    parser = ArgumentParser(description="Enterprise STORM CLI Executor")
    parser.add_argument("--company", type=str, help="분석할 기업명 (Interactive 모드 스킵)")
    parser.add_argument("--topic", type=str, help="분석 주제 (Interactive 모드 스킵)")
    parser.add_argument("--provider", type=str, default="openai", choices=["openai", "gemini"], help="LLM Provider")

    args = parser.parse_args()

    # 0. 개발 편의: Alembic 없이 스키마 생성
    if os.getenv("AUTO_CREATE_SCHEMA") == "1":
        logger.warning("[WARNING] AUTO_CREATE_SCHEMA=1: Creating DB schema from models.")
        await ensure_schema()

    # 1. 입력값 처리 (CLI Argument vs Interactive)
    if args.company and args.topic:
        # Argument 모드: 기업명으로 ID 조회 필요
        db = AsyncDatabaseEngine()
        async with db.get_session() as session:
            repo = CompanyRepository(session)
            comp_obj = await repo.get_by_company_name(args.company)
            if not comp_obj:
                logger.error(f"❌ 기업 '{args.company}'를 찾을 수 없습니다.")
                return
            company_id = comp_obj.id
            company_name = comp_obj.company_name
            topic = args.topic
    else:
        # Interactive 모드
        company_id, company_name, topic = await select_company_and_topic_interactive()

    provider = args.provider
    logger.info(f"🚀 분석 시작: {company_name} - {topic} (Model: {provider})")

    # 2. Job 생성 (PENDING 상태)
    # 파이프라인 실행 전에 DB에 '작업이 생성됨'을 알립니다.
    db = AsyncDatabaseEngine()
    async with db.get_session() as session:
        job_repo = ReportJobRepository(session)
        job_service = ReportJobService(job_repo)

        job_id = await job_service.create_job(company_id=company_id, company_name=company_name, topic=topic)
        logger.info(f"🆔 Job Created: {job_id}")

    # 3. 파이프라인 실행
    # CLI 환경이므로 상태 관리를 위한 로컬 딕셔너리 생성
    # (API 서버에서는 이게 전역 메모리 변수가 됨)
    jobs_dict = {job_id: {"status": ReportJobStatus.PENDING.value, "progress": 0, "message": "Initializing..."}}

    try:
        # [핵심] 모든 로직은 엔진으로 위임
        await run_storm_pipeline(
            job_id=job_id, company_name=company_name, topic=topic, jobs_dict=jobs_dict, model_provider=provider
        )

        # 결과 확인
        final_status = jobs_dict[job_id]
        if final_status["status"] == "COMPLETED":
            logger.info(f"✨ 분석 완료! Report ID: {final_status.get('report_id')}")
        else:
            logger.error(f"🔥 분석 실패: {final_status.get('message')}")

    except KeyboardInterrupt:
        logger.warning("\n🛑 사용자에 의해 중단되었습니다.")
        # 중단 시 DB 상태 업데이트 로직이 필요하다면 여기에 추가 (Service 호출)
    finally:
        await db.dispose()

    if AI_CONFIG.get("storm_force_exit"):
        logger.warning("[WARNING] STORM_FORCE_EXIT=1 is set. Exiting process now.")
        try:
            sys.exit(0)
        finally:
            os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
