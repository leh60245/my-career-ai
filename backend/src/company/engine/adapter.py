"""
STORM Engine DB Adapter (Refactored)
역할:
  1) 파일 시스템에 저장된 STORM 결과물을 읽어 DB에 저장하는 기존 방식
  2) STORM 엔진의 메모리 객체를 직접 받아 파일 재읽기 없이 DB에 저장하는 최적화 방식
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from src.company.repositories.company_repository import CompanyRepository
from src.company.repositories.generated_report_repository import GeneratedReportRepository
from src.company.services.generated_report_service import GeneratedReportService

from .io import find_topic_directory, load_storm_output_files


logger = logging.getLogger(__name__)


async def save_storm_result_to_db(
    session: AsyncSession,
    company_name: str,
    topic: str,
    output_dir: str,
    model_name: str,
    meta_info: dict[str, Any] | None = None,
) -> int | None:
    """
    STORM 결과 디렉토리를 읽어 DB에 저장합니다. (Transaction Safe)
    """
    if meta_info is None:
        meta_info = {}

    job_id = meta_info.get("job_id")
    if not job_id:
        logger.error("❌ Critical Error: 'job_id' is missing in meta_info. Cannot link report to job.")
        return None
    logger.info(f"[{job_id}] 📥 Starting to save results from {output_dir}")

    # 1. 파일 시스템에서 결과 읽기 (IO)
    topic_dir = find_topic_directory(output_dir)
    if not topic_dir:
        logger.error(f"[{job_id}] Cannot find topic directory in {output_dir}")
        return None

    data = load_storm_output_files(topic_dir)

    if not data or not data.get("report_content"):
        logger.error(f"[{job_id}] Report content is empty. Skipping DB save.")
        return None

    # 2. 메타데이터 확장
    final_meta = meta_info.copy()
    final_meta.update({
        "file_path": topic_dir,
        "run_config": data.get("run_config", {}),
    })

    # 3. 서비스 조립 (On-Demand Injection)
    comp_repo = CompanyRepository(session)
    report_repo = GeneratedReportRepository(session)
    report_service = GeneratedReportService(report_repo)

    try:
        company = await comp_repo.get_by_company_name(company_name)
        if not company:
            logger.error(f"[{job_id}] Company '{company_name}' not found in DB.")
            return None

        report = await report_service.create_report(
            job_id=job_id,
            company_name=company_name,
            topic=topic,
            content=data["report_content"],
            model_name=model_name,
            meta_info=final_meta,
            toc_text=data.get("toc_text"),
            references_data=data.get("references"),
            conversation_log=data.get("logs"),
        )

        return report.id

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Failed to save report to DB: {e}")
        raise e


async def save_storm_result_from_memory(
    session: AsyncSession,
    company_name: str,
    topic: str,
    report_content: str,
    toc_text: str | None,
    references_data: dict[str, Any] | None,
    conversation_log: list | dict | None,
    model_name: str,
    meta_info: dict[str, Any] | None = None,
) -> int | None:
    """
    STORM 엔진의 메모리 객체에서 직접 DB에 저장합니다.
    파일 시스템 → 재읽기 단계를 건너뛰어 성능·안정성이 향상됩니다.
    """
    if meta_info is None:
        meta_info = {}

    job_id = meta_info.get("job_id")
    if not job_id:
        logger.error("❌ 'job_id' missing in meta_info")
        return None

    if not report_content:
        logger.error(f"[{job_id}] Report content is empty.")
        return None

    logger.info(f"[{job_id}] 📥 Saving STORM results directly from memory")

    comp_repo = CompanyRepository(session)
    report_repo = GeneratedReportRepository(session)
    report_service = GeneratedReportService(report_repo)

    try:
        company = await comp_repo.get_by_company_name(company_name)
        if not company:
            logger.error(f"[{job_id}] Company '{company_name}' not found in DB.")
            return None

        # conversation_log가 list인 경우 dict로 래핑 (JSON 컬럼 호환)
        conv_log = conversation_log
        if isinstance(conversation_log, list):
            conv_log = {"conversations": conversation_log}

        report = await report_service.create_report(
            job_id=job_id,
            company_name=company_name,
            topic=topic,
            content=report_content,
            model_name=model_name,
            meta_info=meta_info,
            toc_text=toc_text,
            references_data=references_data,
        )

        logger.info(f"[{job_id}] ✅ Report saved from memory: ID {report.id}")
        return report.id

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Failed to save report from memory: {e}")
        raise e
