"""
Company 도메인 테스트

기업 조회, 기업 분석 요청 플로우 등의 해피패스 및 예외 상황을 검증.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ReportJobStatus
from backend.src.company.models.company import Company
from backend.src.company.services.company_service import CompanyService
from backend.src.company.services.report_job_service import ReportJobService
from backend.src.user.models import User


# ============================================================
# CompanyService 단위 테스트
# ============================================================
class TestCompanyService:
    """CompanyService 단위 테스트."""

    async def test_onboard_company_creates_new(self, session: AsyncSession):
        """새로운 기업을 등록한다."""
        service = CompanyService.from_session(session)
        company = await service.onboard_company(
            corp_code="12345678", company_name="신규기업주식회사", stock_code=None, sector="IT", product="소프트웨어"
        )

        assert company is not None
        assert company.id is not None
        assert company.corp_code == "12345678"
        assert company.company_name == "신규기업주식회사"

    async def test_onboard_company_idempotent(self, session: AsyncSession):
        """동일 corp_code로 두 번 등록하면 기존 레코드를 반환한다 (Idempotent)."""
        service = CompanyService.from_session(session)
        first = await service.onboard_company(corp_code="87654321", company_name="기존기업")
        second = await service.onboard_company(corp_code="87654321", company_name="기존기업2")

        # 동일한 ID를 가져야 함 (업데이트)
        assert first.id == second.id

    async def test_onboard_company_missing_corp_code(self, session: AsyncSession):
        """corp_code 없이 등록 시 ValueError가 발생한다."""
        service = CompanyService.from_session(session)

        with pytest.raises(ValueError, match="corp_code"):
            await service.onboard_company(corp_code="", company_name="테스트기어")

    async def test_search_companies(self, session: AsyncSession, test_company: Company):
        """기업명 부분 검색이 동작한다."""
        service = CompanyService.from_session(session)
        results = await service.search_by_name("테스트기업")

        assert len(results) >= 1
        assert any(c.company_name == test_company.company_name for c in results)

    async def test_get_all_companies(self, session: AsyncSession, test_company: Company):
        """전체 기업 목록을 조회한다."""
        service = CompanyService.from_session(session)
        companies = await service.get_all_companies(limit=100)

        assert isinstance(companies, list)
        assert len(companies) >= 1


# ============================================================
# Company API 엔드포인트 테스트
# ============================================================
class TestCompanyAPI:
    """Company API 통합 테스트."""

    async def test_get_companies(self, client: AsyncClient, test_company: Company):
        """GET /api/companies — 기업 목록 조회 성공."""
        response = await client.get("/api/companies")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_search_company_found(self, client: AsyncClient, test_company: Company):
        """GET /api/company/search — 기업명 검색 성공."""
        response = await client.get("/api/company/search", params={"query": "테스트기업"})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(c["company_name"] == test_company.company_name for c in data)

    async def test_search_company_empty_result(self, client: AsyncClient):
        """GET /api/company/search — 존재하지 않는 기업 검색 시 빈 목록 반환."""
        response = await client.get("/api/company/search", params={"query": "절대존재안하는기업이름XYZABC123"})

        assert response.status_code == 200
        data = response.json()
        assert data == []

    async def test_get_topics(self, client: AsyncClient):
        """GET /api/topics — 분석 주제 목록 반환."""
        response = await client.get("/api/topics")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]
        assert "label" in data[0]

    async def test_get_trending_companies(self, client: AsyncClient, test_company: Company):
        """GET /api/company/trending — 최근 분석 기업 목록 반환."""
        response = await client.get("/api/company/trending")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================
# ReportJobService 단위 테스트
# ============================================================
class TestReportJobService:
    """ReportJobService 비즈니스 로직 단위 테스트."""

    async def test_create_job_success(self, session: AsyncSession, test_company: Company, job_seeker_user: User):
        """분석 요청을 성공적으로 등록한다."""
        service = ReportJobService.from_session(session)
        job_id = await service.create_job(
            company_id=test_company.id, company_name=test_company.company_name, topic="채용정보"
        )

        assert job_id is not None
        assert len(job_id) > 0

        # DB에서 확인
        job = await service.get_job(job_id)
        assert job is not None
        assert job.status == ReportJobStatus.PENDING

    async def test_start_job(self, session: AsyncSession, test_company: Company):
        """분석 작업을 PROCESSING 상태로 변경한다."""
        service = ReportJobService.from_session(session)
        job_id = await service.create_job(company_id=test_company.id, company_name="기업명", topic="topic")

        await service.start_job(job_id)
        job = await service.get_job(job_id)
        assert job.status == ReportJobStatus.PROCESSING

    async def test_complete_job(self, session: AsyncSession, test_company: Company):
        """분석 작업을 COMPLETED 상태로 변경한다."""
        service = ReportJobService.from_session(session)
        job_id = await service.create_job(company_id=test_company.id, company_name="기업명", topic="topic")

        await service.start_job(job_id)
        await service.complete_job(job_id)
        job = await service.get_job(job_id)
        assert job.status == ReportJobStatus.COMPLETED

    async def test_fail_job(self, session: AsyncSession, test_company: Company):
        """분석 작업 실패 시 FAILED 상태 및 에러 메시지를 기록한다."""
        service = ReportJobService.from_session(session)
        job_id = await service.create_job(company_id=test_company.id, company_name="기업명", topic="topic")

        await service.fail_job(job_id, "테스트 에러 메시지")
        job = await service.get_job(job_id)
        assert job.status == ReportJobStatus.FAILED
        assert job.error_message == "테스트 에러 메시지"

    async def test_get_job_not_found(self, session: AsyncSession):
        """존재하지 않는 job_id 조회 시 None을 반환한다."""
        service = ReportJobService.from_session(session)
        job = await service.get_job("00000000-0000-0000-0000-000000000000")
        assert job is None

    async def test_list_jobs(self, session: AsyncSession, test_company: Company):
        """전체 작업 목록을 페이지네이션으로 조회한다."""
        service = ReportJobService.from_session(session)
        await service.create_job(company_id=test_company.id, company_name="기업명A", topic="topic1")
        await service.create_job(company_id=test_company.id, company_name="기업명B", topic="topic2")

        total, jobs = await service.list_jobs(limit=10, offset=0)
        assert total >= 2
        assert len(jobs) >= 2
