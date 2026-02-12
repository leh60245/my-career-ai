import logging
from typing import Any

from src.company_analysis.models.analysis_report import AnalysisReport
from src.company_analysis.repositories.analysis_report_repository import AnalysisReportRepository
from src.company_analysis.repositories.company_repository import CompanyRepository


logger = logging.getLogger(__name__)


class AnalysisService:
    """
    분석 보고서 메타데이터 관리 서비스 (The Librarian)
    역할: 보고서의 메타데이터(접수번호, 날짜 등)를 저장하고 중복을 방지합니다.
    """

    def __init__(self, report_repo: AnalysisReportRepository, company_repo: CompanyRepository):
        self.report_repo = report_repo
        self.company_repo = company_repo

    async def save_report_metadata(
        self, company_id: int, data: dict[str, Any], return_existing: bool = True
    ) -> AnalysisReport:
        """
        보고서 메타데이터 저장 (중복 방지 로직 포함)

        Args:
            company_id: 소속 기업 ID (FK)
            data: DartService에서 추출한 메타데이터 (rcept_no 필수)
            return_existing: True면 이미 존재할 경우 해당 객체 반환, False면 에러 발생

        Returns:
            AnalysisReport: 저장된(혹은 조회된) 보고서 객체
        """
        # 1. 필수값 검증
        rcept_no = data.get("rcept_no")
        if not rcept_no:
            raise ValueError("rcept_no(접수번호) is required for saving report metadata.")

        # 2. [Read] 중복 체크 (접수번호 기준)
        # DART 접수번호는 절대 고유하므로 이를 기준으로 판단
        existing = await self.report_repo.get_by_rcept_no(rcept_no)

        if existing:
            if return_existing:
                logger.info(f"   ℹ️ Report already exists: {data.get('title')} ({rcept_no})")
                return existing
            else:
                raise ValueError(f"Report {rcept_no} already exists.")

        # 3. [Create] 신규 저장
        # 모델 스키마에 맞춰 데이터 매핑
        report_data = {
            "company_id": company_id,
            "title": data.get("title", "Untitled"),
            "rcept_no": rcept_no,
            "rcept_dt": data.get("rcept_dt"),
            "report_type": data.get("report_type", "annual"),
            "status": "PENDING",
        }

        new_report = await self.report_repo.create(report_data)
        logger.info(f"   ✨ Saved report metadata: {new_report.title}")

        return new_report

    async def get_report(self, report_id: int) -> AnalysisReport | None:
        return await self.report_repo.get(report_id)
