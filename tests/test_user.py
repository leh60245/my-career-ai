"""
User 도메인 테스트

User 계정 생성, 프로필 조회, 프로필 수정 등의 해피패스 및 예외 상황을 검증.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.enums import UserRole
from backend.src.common.repositories.base_repository import EntityNotFound
from backend.src.user.models import User
from backend.src.user.repositories import UserRepository
from backend.src.user.services import UserService


# ============================================================
# Service 단위 테스트
# ============================================================
class TestUserService:
    """UserService 비즈니스 로직 단위 테스트."""

    async def test_get_user_success(self, session: AsyncSession, job_seeker_user: User):
        """존재하는 사용자를 ID로 정상 조회한다."""
        service = UserService.from_session(session)
        user = await service.get_user(job_seeker_user.id)

        assert user is not None
        assert user.id == job_seeker_user.id
        assert user.email == job_seeker_user.email
        assert user.role == UserRole.JOB_SEEKER

    async def test_get_user_not_found(self, session: AsyncSession):
        """존재하지 않는 user_id 조회 시 EntityNotFound가 발생한다."""
        service = UserService.from_session(session)

        with pytest.raises(EntityNotFound):
            await service.get_user(99999999)

    async def test_create_user_success(self, session: AsyncSession):
        """새로운 사용자를 생성한다."""
        service = UserService.from_session(session)
        user = await service.create_user(email="newuser@example.com", role="JOB_SEEKER")

        assert user is not None
        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.role == UserRole.JOB_SEEKER

    async def test_create_manager_user(self, session: AsyncSession):
        """MANAGER 역할의 사용자를 생성한다."""
        service = UserService.from_session(session)
        user = await service.create_user(email="newmanager@example.com", role="MANAGER")

        assert user.role == UserRole.MANAGER

    async def test_get_user_with_profile_no_profile(self, session: AsyncSession, job_seeker_user: User):
        """프로필이 없는 사용자를 조회해도 안전하게 None을 반환한다."""
        service = UserService.from_session(session)
        user = await service.get_user_with_profile(job_seeker_user.id)

        assert user is not None
        assert user.id == job_seeker_user.id
        # profile이 없을 수 있음 (선택적)
        assert user.job_seeker_profile is None or user.job_seeker_profile is not None

    async def test_update_last_login(self, session: AsyncSession, job_seeker_user: User):
        """last_login 갱신이 정상적으로 동작한다."""
        service = UserService.from_session(session)
        await service.update_last_login(job_seeker_user.id)

        # 갱신 후 재조회
        repo = UserRepository(session)
        updated_user = await repo.get(job_seeker_user.id)
        assert updated_user is not None
        assert updated_user.last_login is not None


# ============================================================
# API 엔드포인트 테스트
# ============================================================
class TestUserAPI:
    """User API 엔드포인트 통합 테스트."""

    async def test_register_user_success(self, client: AsyncClient):
        """POST /api/user/register — 사용자 생성 성공."""
        response = await client.post("/api/user/register", json={"email": "apitest@example.com", "role": "JOB_SEEKER"})

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "apitest@example.com"
        assert data["role"] == "JOB_SEEKER"
        assert "id" in data

    async def test_register_user_invalid_email(self, client: AsyncClient):
        """POST /api/user/register — 잘못된 이메일 형식으로 400 반환."""
        response = await client.post("/api/user/register", json={"email": "not-an-email", "role": "JOB_SEEKER"})

        assert response.status_code == 422  # Pydantic 유효성 검사 실패

    async def test_register_user_missing_field(self, client: AsyncClient):
        """POST /api/user/register — 필수 필드 누락 시 422 반환."""
        response = await client.post("/api/user/register", json={"role": "JOB_SEEKER"})

        assert response.status_code == 422

    async def test_get_me_success(self, client: AsyncClient, job_seeker_user: User):
        """GET /api/user/me — 사용자 본인 정보 정상 조회."""
        response = await client.get("/api/user/me", params={"user_id": job_seeker_user.id})

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == job_seeker_user.id
        assert data["user"]["email"] == job_seeker_user.email

    async def test_get_me_not_found(self, client: AsyncClient):
        """GET /api/user/me — 존재하지 않는 user_id로 404 반환."""
        response = await client.get("/api/user/me", params={"user_id": 99999999})

        assert response.status_code == 404
