import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.company.models.generated_report import GeneratedReport
from backend.src.company.repositories.generated_report_repository import GeneratedReportRepository


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
        conversation_log: list | dict | None = None,
    ) -> GeneratedReport:
        """
        STORM 결과물을 DB에 저장

        Args:
            job_id: STORM 작업 UUID
            company_name: 분석 대상 기업명
            topic: 분석 주제
            content: 리포트 본문 (Markdown)
            model_name: 사용된 LLM 모델명
            meta_info: 부가 메타정보 (파일 경로, 설정 등)
            toc_text: 목차 텍스트
            references_data: 참고문헌 데이터 (url_to_unified_index 등)
            conversation_log: 페르소나 대화 로그 (STORM 연구 대화)
        """
        if meta_info is None:
            meta_info = {}

        # conversation_log가 list인 경우 dict로 래핑 (JSON 컬럼 호환)
        conv_log = conversation_log
        if isinstance(conversation_log, list):
            conv_log = {"conversations": conversation_log}

        report_data = {
            "job_id": job_id,
            "company_name": company_name,
            "topic": topic,
            "report_content": content,
            "model_name": model_name,
            "meta_info": meta_info,
            "toc_text": toc_text,
            "references_data": references_data,
            "conversation_log": conv_log,
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

    async def get_reports_by_company_name(self, company_name: str) -> list[GeneratedReport]:
        """특정 기업의 모든 생성 리포트를 조회한다."""
        reports = await self.repository.get_by_company_name(company_name)
        return list(reports)
