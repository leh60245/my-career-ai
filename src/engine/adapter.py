"""
STORM Engine DB Adapter (Refactored)
역할: 파일 시스템에 저장된 STORM 결과물(Markdown, Logs)을 읽어서 
      GeneratedReportService를 통해 DB에 저장합니다.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Local Imports
from src.engine.io import find_topic_directory, load_storm_output_files
from src.repositories import CompanyRepository, GeneratedReportRepository
from src.services.generated_report_service import GeneratedReportService

logger = logging.getLogger(__name__)

async def save_storm_result_to_db(
    session: AsyncSession,  # [핵심] 외부에서 주입된 세션 사용
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

    # load_storm_output_files 함수가 { "report_content": "...", "sources": ... } 등을 반환한다고 가정
    data = load_storm_output_files(topic_dir)

    if not data or not data.get("report_content"):
        logger.error(f"[{job_id}] Report content is empty. Skipping DB save.")
        return None

    # 2. 메타데이터 확장
    # 파일에서 읽은 추가 정보들(참고문헌 등)을 메타데이터에 병합
    final_meta = meta_info.copy()
    final_meta.update({
        "file_path": topic_dir,
        "toc": data.get("toc_text", ""),
        "references": data.get("references", []),
        "run_config": data.get("run_config", {})
    })

    # 3. 서비스 조립 (On-Demand Injection)
    # 이미 열려있는 session을 사용하여 Repository와 Service를 만듭니다.
    comp_repo = CompanyRepository(session)
    report_repo = GeneratedReportRepository(session)
    report_service = GeneratedReportService(report_repo)

    try:
        # 3-1. Company ID 조회 (ID가 없다면 이름으로 조회)
        company = await comp_repo.get_by_company_name(company_name)
        if not company:
            logger.error(f"[{job_id}] Company '{company_name}' not found in DB.")
            return None



        # 3-2. 리포트 저장 요청
        report = await report_service.create_report(
            job_id=job_id,
            company_name=company_name,
            topic=topic,
            content=data["report_content"],
            model_name=model_name,
            meta_info=final_meta,
            toc_text=data.get("toc_text"),
            references_data=data.get("references"),
        )

        return report.id

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Failed to save report to DB: {e}")
        # 세션은 파이프라인이 관리하므로 여기서 rollback이나 close를 하지 않습니다.
        # 에러만 전파(raise)하거나 로그 남기고 None 리턴
        raise e
