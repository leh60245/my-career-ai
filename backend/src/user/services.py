"""
User 도메인 Service

사용자 계정 조회, 프로필 관리 로직.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.common.repositories.base_repository import EntityNotFound
from backend.src.user.models import User
from backend.src.user.repositories import JobSeekerProfileRepository, UserRepository


logger = logging.getLogger(__name__)


class UserService:
    """
    사용자 서비스.

    계정 조회, 프로필 수정 등 User 도메인의 핵심 비즈니스 로직.
    """

    def __init__(self, user_repo: UserRepository, profile_repo: JobSeekerProfileRepository) -> None:
        self.user_repo = user_repo
        self.profile_repo = profile_repo

    @classmethod
    def from_session(cls, session: AsyncSession) -> "UserService":
        """AsyncSession으로부터 서비스 인스턴스를 생성한다."""
        return cls(user_repo=UserRepository(session), profile_repo=JobSeekerProfileRepository(session))

    async def get_user_with_profile(self, user_id: int) -> User:
        """
        사용자 정보와 프로필을 함께 조회한다.

        Args:
            user_id: 사용자 PK

        Returns:
            User (프로필 eager-loaded)

        Raises:
            EntityNotFound: 사용자가 존재하지 않는 경우
        """
        user = await self.user_repo.get_with_profile(user_id)
        if not user:
            raise EntityNotFound(f"User(id={user_id}) 이(가) 존재하지 않습니다.")
        return user

    async def update_job_seeker_profile(self, user_id: int, data: dict) -> None:
        """
        구직자 프로필을 수정한다.

        Args:
            user_id: 사용자 PK
            data: 수정할 필드 dict (student_id, education, specs)

        Raises:
            EntityNotFound: 프로필이 존재하지 않는 경우
        """
        profile = await self.profile_repo.get(user_id)
        if not profile:
            raise EntityNotFound(f"JobSeekerProfile(user_id={user_id}) 이(가) 존재하지 않습니다.")

        # None이 아닌 필드만 업데이트
        update_data = {k: v for k, v in data.items() if v is not None}
        if update_data:
            await self.profile_repo.update(user_id, update_data)

    async def create_user(self, email: str, role: str = "JOB_SEEKER") -> User:
        """
        사용자를 생성한다 (개발/테스트용).

        Args:
            email: 이메일
            role: 사용자 역할

        Returns:
            생성된 User
        """
        user = await self.user_repo.create({"email": email, "role": role, "tier": "FREE"})
        logger.info(f" 사용자 생성: {email} (role={role})")
        return user

    async def update_last_login(self, user_id: int) -> None:
        """
        마지막 로그인 시각을 갱신한다.

        Args:
            user_id: 사용자 PK
        """
        await self.user_repo.update(user_id, {"last_login": datetime.now(UTC)})
