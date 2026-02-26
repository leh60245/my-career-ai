"""
골든 데이터셋 DB 인제스션 스크립트

golden_dataset/ 디렉토리의 5개 기업 분석 JSON 파일을 generated_reports 테이블에 삽입합니다.
기업이 companies 테이블에 없으면 자동 생성합니다.

Usage:
    conda activate enterprise-storm
    python -m scripts.seed_golden_dataset
"""

import asyncio
import json
import os
import uuid

# SQLAlchemy ORM relationship 해석을 위해 User 모델 임포트 필수
import backend.src.user.models  # noqa: F401
from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.generated_report_repository import GeneratedReportRepository
from backend.src.company.repositories.report_job_repository import ReportJobRepository
from backend.src.company.services.generated_report_service import GeneratedReportService
from backend.src.company.services.report_job_service import ReportJobService


GOLDEN_DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "golden_dataset")

# 파일명 -> (기업명, corp_code) 매핑
COMPANY_FILES = {
    "삼성전자.json": ("삼성전자", "00126380"),
    "현대자동차.json": ("현대자동차", "00164742"),
    "BGF리테일.json": ("BGF리테일", "01163230"),
    "CJ_ENM.json": ("CJ ENM", "00984497"),
    "KG모빌리티.json": ("KG모빌리티", "00382199"),
}


async def ensure_company_exists(session, company_name: str, corp_code: str) -> int:
    """기업이 companies 테이블에 없으면 생성합니다."""
    comp_repo = CompanyRepository(session)
    company = await comp_repo.get_by_company_name(company_name)
    if company:
        print(f"  [OK] 기업 '{company_name}' 존재 (ID={company.id})")
        return company.id

    # 기업 생성
    from backend.src.company.models.company import Company

    new_company = Company(company_name=company_name, corp_code=corp_code)
    session.add(new_company)
    await session.flush()
    print(f"  [NEW] 기업 '{company_name}' 생성 (ID={new_company.id})")
    return new_company.id


async def seed_golden_dataset():
    """골든 데이터셋을 DB에 인제스션합니다."""
    engine = AsyncDatabaseEngine()
    await engine.initialize()

    print("=" * 60)
    print("Golden Dataset DB Ingestion")
    print("=" * 60)

    for filename, (company_name, corp_code) in COMPANY_FILES.items():
        filepath = os.path.join(GOLDEN_DATASET_DIR, filename)
        if not os.path.exists(filepath):
            print(f"[SKIP] 파일 없음: {filepath}")
            continue

        print(f"\n--- {company_name} ({filename}) ---")

        with open(filepath, encoding="utf-8") as f:
            golden_data = json.load(f)

        # JSON 문자열로 변환 (report_content 필드에 저장)
        report_content_json = json.dumps(golden_data, ensure_ascii=False, indent=2)

        async with engine.get_session() as session:
            # 1. 기업 존재 확인/생성
            company_id = await ensure_company_exists(session, company_name, corp_code)

            # 2. 이미 인제스션된 리포트 확인
            report_repo = GeneratedReportRepository(session)
            from sqlalchemy import select

            from backend.src.company.models.generated_report import GeneratedReport

            existing = await session.execute(
                select(GeneratedReport).where(
                    GeneratedReport.company_name == company_name, GeneratedReport.topic == "Career AI 종합 분석"
                )
            )
            if existing.scalars().first():
                print(f"  [SKIP] '{company_name}' Career AI 종합 분석 리포트 이미 존재")
                continue

            # 3. ReportJob 생성 (FK 요구사항 충족)
            job_repo = ReportJobRepository(session)
            job_service = ReportJobService(job_repo)
            job_id = str(uuid.uuid4())[:8] + "-golden"
            from backend.src.common.enums import ReportJobStatus
            from backend.src.company.models.report_job import ReportJob

            job = ReportJob(
                id=f"golden-{job_id}",
                company_id=company_id,
                company_name=company_name,
                topic="Career AI 종합 분석",
                status=ReportJobStatus.COMPLETED,
            )
            session.add(job)
            await session.flush()

            # 4. GeneratedReport 생성
            report_service = GeneratedReportService(report_repo)
            report = await report_service.create_report(
                job_id=job.id,
                company_name=company_name,
                topic="Career AI 종합 분석",
                content=report_content_json,
                model_name="golden-dataset",
                meta_info={"source": "golden_dataset", "filename": filename},
                toc_text=None,
                references_data=None,
                conversation_log=None,
            )

            await session.commit()
            print(f"  [OK] 리포트 저장 완료 (ID={report.id}, job_id={job.id})")

    print("\n" + "=" * 60)
    print("Ingestion Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_golden_dataset())
