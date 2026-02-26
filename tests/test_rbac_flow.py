"""
기업 분석 요청 플로우 및 RBAC 통합 테스트

wishlist.md의 핵심 요구사항 검증:
  - Happy Path: 구직자 요청 → 관리자 승인 → 상태 변경
  - Edge Case: 중복 요청 차단, 403 권한 우회 방어, 반려 사유 저장
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import ReportJobStatus
from backend.src.common.middlewares.auth import check_admin_permission
from backend.src.common.repositories.base_repository import DuplicateEntity, EntityNotFound
from backend.src.company.models.company import Company
from backend.src.company.services.report_job_service import ReportJobService
from backend.src.user.models import User


# ============================================================
# Service 레벨 — RBAC 플로우 단위 테스트
# ============================================================
class TestAnalysisRequestFlow:
    """기업 분석 요청 플로우 단위 테스트 (Service Layer)."""

    async def test_submit_request_happy_path(self, session: AsyncSession, job_seeker_user: User, test_company: Company):
        """구직자가 분석 요청을 정상 등록하면 PENDING 상태로 저장된다."""
        service = ReportJobService.from_session(session)

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        assert job_id is not None

        job = await service.get_job(job_id)
        assert job is not None
        assert job.status == ReportJobStatus.PENDING
        assert job.user_id == job_seeker_user.id
        assert job.requested_at is not None

    async def test_submit_duplicate_request_blocked(
        self, session: AsyncSession, job_seeker_user: User, test_company: Company
    ):
        """동일 기업에 이미 PENDING 요청이 있으면 중복 요청을 차단한다."""
        service = ReportJobService.from_session(session)

        # 첫 번째 요청 등록
        await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        # 두 번째 중복 요청 시 예외 발생
        with pytest.raises(DuplicateEntity):
            await service.submit_analysis_request(
                user_id=job_seeker_user.id,
                company_id=test_company.id,
                company_name=test_company.company_name,
                topic="기업문화",
            )

    async def test_approve_request_changes_status(
        self, session: AsyncSession, job_seeker_user: User, manager_user: User, test_company: Company
    ):
        """관리자가 승인하면 상태가 PROCESSING으로 변경되고 승인자 정보가 저장된다."""
        service = ReportJobService.from_session(session)

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        await service.approve_request(job_id, approved_by_user_id=manager_user.id)

        job = await service.get_job(job_id)
        assert job.status == ReportJobStatus.PROCESSING
        assert job.approved_by == manager_user.id
        assert job.approved_at is not None

    async def test_reject_request_saves_reason(
        self, session: AsyncSession, job_seeker_user: User, manager_user: User, test_company: Company
    ):
        """관리자가 반려하면 상태가 REJECTED로 변경되고 반려 사유가 저장된다."""
        service = ReportJobService.from_session(session)

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        rejection_reason = "해당 기업 정보를 수집할 수 없습니다."
        await service.reject_request(job_id, approved_by_user_id=manager_user.id, rejection_reason=rejection_reason)

        job = await service.get_job(job_id)
        assert job.status == ReportJobStatus.REJECTED
        assert job.rejection_reason == rejection_reason
        assert job.rejected_at is not None
        assert job.approved_by == manager_user.id

    async def test_approve_already_processed_fails(
        self, session: AsyncSession, job_seeker_user: User, manager_user: User, test_company: Company
    ):
        """이미 처리된(REJECTED) 요청을 다시 승인하면 EntityNotFound가 발생한다."""
        service = ReportJobService.from_session(session)

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        # 먼저 반려
        await service.reject_request(job_id, manager_user.id, "반려합니다")

        # 반려된 요청을 승인 시도 → 실패해야 함
        with pytest.raises(EntityNotFound):
            await service.approve_request(job_id, manager_user.id)

    async def test_get_user_requests(self, session: AsyncSession, job_seeker_user: User, test_company: Company):
        """구직자는 자신의 요청 목록을 조회할 수 있다."""
        service = ReportJobService.from_session(session)

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        requests = await service.get_user_requests(job_seeker_user.id)
        assert len(requests) >= 1
        assert any(r.id == job_id for r in requests)

    async def test_get_pending_requests(self, session: AsyncSession, job_seeker_user: User, test_company: Company):
        """관리자는 대기 중인 모든 요청을 조회할 수 있다."""
        service = ReportJobService.from_session(session)

        await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )

        pending = await service.get_pending_requests()
        assert len(pending) >= 1
        assert all(r.status == ReportJobStatus.PENDING for r in pending)


# ============================================================
# 권한 검증 미들웨어 테스트
# ============================================================
class TestRBACPermission:
    """RBAC 권한 제어 단위 테스트."""

    async def test_admin_permission_granted_for_manager(self, session: AsyncSession, manager_user: User):
        """MANAGER 역할의 사용자는 admin 권한을 통과한다."""
        # 예외 없이 완료되어야 함
        await check_admin_permission(manager_user.id, session)

    async def test_admin_permission_denied_for_job_seeker(self, session: AsyncSession, job_seeker_user: User):
        """JOB_SEEKER 역할의 사용자는 admin 권한 검증에서 403이 발생한다."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(job_seeker_user.id, session)

        assert exc_info.value.status_code == 403

    async def test_admin_permission_denied_for_nonexistent_user(self, session: AsyncSession):
        """존재하지 않는 사용자는 404가 발생한다."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(99999999, session)

        assert exc_info.value.status_code == 404


# ============================================================
# API 레벨 — 403 권한 우회 방어 테스트
# ============================================================
class TestAdminAPIProtection:
    """관리자 API 엔드포인트의 권한 방어 테스트."""

    async def test_approve_by_non_admin_returns_403(
        self, client: AsyncClient, session: AsyncSession, job_seeker_user: User, test_company: Company
    ):
        """
        구직자가 직접 분석 승인 API를 호출하면 403 Forbidden이 반환된다.

        권한 우회 방어(중요) 검증: 일반 사용자는 백엔드 admin API를 우회할 수 없음.
        """
        service = ReportJobService.from_session(session)
        await session.flush()

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )
        await session.flush()

        # 구직자 ID로 관리자 승인 API 호출 (권한 없음)
        response = await client.post(
            f"/api/admin/analyze/{job_id}/approve", json={"approved_by_user_id": job_seeker_user.id}
        )

        assert response.status_code == 403

    async def test_reject_by_non_admin_returns_403(
        self, client: AsyncClient, session: AsyncSession, job_seeker_user: User, test_company: Company
    ):
        """
        구직자가 직접 분석 반려 API를 호출하면 403 Forbidden이 반환된다.
        """
        service = ReportJobService.from_session(session)
        await session.flush()

        job_id = await service.submit_analysis_request(
            user_id=job_seeker_user.id,
            company_id=test_company.id,
            company_name=test_company.company_name,
            topic="채용정보",
        )
        await session.flush()

        response = await client.post(
            f"/api/admin/analyze/{job_id}/reject",
            json={"approved_by_user_id": job_seeker_user.id, "rejection_reason": "우회 시도"},
        )

        assert response.status_code == 403

    async def test_get_pending_requests_by_non_admin_returns_403(self, client: AsyncClient, job_seeker_user: User):
        """구직자가 관리자용 대기 요청 목록 조회 시 403 반환."""
        response = await client.get("/api/admin/analyze/requests", params={"user_id": job_seeker_user.id})

        assert response.status_code == 403

    async def test_submit_analysis_request_api(
        self, client: AsyncClient, session: AsyncSession, job_seeker_user: User, test_company: Company
    ):
        """POST /api/company/analyze/request — 구직자의 분석 요청 등록 성공."""
        await session.flush()

        response = await client.post(
            "/api/company/analyze/request",
            params={"user_id": job_seeker_user.id},
            json={"company_id": test_company.id, "company_name": test_company.company_name, "topic": "채용정보"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "PENDING"
        # validation_alias="id"는 ORM의 .id 속성에서 읽기 전용. JSON 직렬화는 필드명 "job_id"를 사용
        assert "job_id" in data

    async def test_submit_duplicate_request_api_blocked(
        self, client: AsyncClient, session: AsyncSession, job_seeker_user: User, test_company: Company
    ):
        """동일 기업 중복 요청 시 400 Bad Request 반환."""
        await session.flush()

        payload = {"company_id": test_company.id, "company_name": test_company.company_name, "topic": "채용정보"}
        params = {"user_id": job_seeker_user.id}

        # 첫 번째 요청
        first = await client.post("/api/company/analyze/request", params=params, json=payload)
        assert first.status_code == 201

        # 두 번째 중복 요청
        second = await client.post("/api/company/analyze/request", params=params, json=payload)
        assert second.status_code == 400
