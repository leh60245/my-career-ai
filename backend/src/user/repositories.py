"""
User 도메인 Repositories

사용자 계정, 구직자 프로필, 관리자 프로필, 소속 관련 데이터 접근 계층.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.user.models import Affiliation, JobSeekerProfile, User


logger = logging.getLogger(__name__)


# ============================================================
# User Repository
# ============================================================
class UserRepository(BaseRepository[User]):
    """통합 사용자 계정 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """
        이메일로 사용자를 조회한다.

        Args:
            email: 이메일 주소

        Returns:
            User 인스턴스 또는 None
        """
        stmt = select(self.model).where(self.model.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_profile(self, user_id: int) -> User | None:
        """
        사용자를 프로필(구직자/관리자) 포함하여 조회한다.

        Args:
            user_id: 사용자 PK

        Returns:
            User (프로필 eager-loaded) 또는 None
        """
        stmt = (
            select(self.model)
            .where(self.model.id == user_id)
            .options(selectinload(self.model.job_seeker_profile), selectinload(self.model.manager_profile))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ============================================================
# JobSeekerProfile Repository
# ============================================================
class JobSeekerProfileRepository(BaseRepository[JobSeekerProfile]):
    """구직자 프로필 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(JobSeekerProfile, session)

    async def get_by_user_id(self, user_id: int) -> JobSeekerProfile | None:
        """
        사용자 ID로 구직자 프로필을 조회한다.

        Args:
            user_id: 사용자 PK (= 프로필 PK)

        Returns:
            JobSeekerProfile 또는 None
        """
        return await self.get(user_id)


# ============================================================
# Affiliation Repository
# ============================================================
class AffiliationRepository(BaseRepository[Affiliation]):
    """소속 기관 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Affiliation, session)

    async def get_by_domain(self, domain: str) -> Affiliation | None:
        """
        이메일 도메인으로 소속 기관을 조회한다.

        Args:
            domain: 이메일 도메인 (e.g., snu.ac.kr)

        Returns:
            Affiliation 또는 None
        """
        stmt = select(self.model).where(self.model.domain == domain)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
