import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import GeneratedReport
from src.repositories.generated_report_repository import \
    GeneratedReportRepository

logger = logging.getLogger(__name__)


class GeneratedReportService:
    """
    최종 생성된 리포트(Markdown)를 DB에 저장하고 관리하는 서비스
    """

    def __init__(self, repository: GeneratedReportRepository):
        self.repository = repository

    @classmethod
    def from_session(cls, session: AsyncSession) -> "GeneratedReportService":
        """AsyncSession으로부터 서비스 인스턴스 생성 (Controller용)"""
        return cls(GeneratedReportRepository(session))

    async def create_report(
        self,
        job_id: str,
        company_name: str,
        topic: str,
        content: str,
        model_name: str,
        meta_info: dict[str, Any] | None = None,
        toc_text: str | None = None,
        references_data: dict[str, Any] | None = None,
        conversation_log: dict[str, Any] | None = None,
    ) -> GeneratedReport:
        """
        STORM 결과물을 DB에 저장
        """
        if meta_info is None:
            meta_info = {}

        report_data = {
            "job_id": job_id,
            "company_name": company_name,
            "topic": topic,
            "report_content": content,
            "model_name": model_name,
            "meta_info": meta_info,
            "toc_text": toc_text,
            "references_data": references_data,
            "conversation_log": conversation_log,
        }

        # DB 저장
        report = await self.repository.create(report_data)
        logger.info(f"💾 Generated Report Saved: ID {report.id} (Job: {job_id})")
        return report

    async def get_report(self, report_id: int) -> GeneratedReport | None:
        """리포트 ID(PK)로 단건 조회"""
        return await self.repository.get(report_id)

    async def get_report_by_job_id(self, job_id: str) -> GeneratedReport | None:
        """Job ID로 리포트 조회 (1:1 관계)"""
        return await self.repository.get_by_job_id(job_id)
