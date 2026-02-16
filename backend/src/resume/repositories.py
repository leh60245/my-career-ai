"""
Resume 도메인 Repositories

4-Tier 모델(Question → Item → Draft → Feedback)에 대한 데이터 접근 계층.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.src.common.repositories.base_repository import BaseRepository
from backend.src.resume.models import ResumeDraft, ResumeFeedback, ResumeItem, ResumeQuestion


logger = logging.getLogger(__name__)


# ============================================================
# ResumeQuestion Repository
# ============================================================
class ResumeQuestionRepository(BaseRepository[ResumeQuestion]):
    """자소서 세트 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ResumeQuestion, session)

    async def get_by_user_id(self, user_id: int, include_archived: bool = False) -> Sequence[ResumeQuestion]:
        """
        사용자의 자소서 세트 목록을 조회한다.

        Args:
            user_id: 사용자 PK
            include_archived: 아카이브된 항목 포함 여부

        Returns:
            자소서 세트 목록 (최신순)
        """
        stmt = select(self.model).where(self.model.user_id == user_id)

        if not include_archived:
            stmt = stmt.where(self.model.is_archived.is_(False))

        stmt = stmt.order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_with_items(self, question_id: int) -> ResumeQuestion | None:
        """
        자소서 세트를 문항(items)과 함께 한 번에 로드한다.

        Args:
            question_id: 자소서 세트 PK

        Returns:
            ResumeQuestion (items 포함) 또는 None
        """
        stmt = select(self.model).where(self.model.id == question_id).options(selectinload(self.model.items))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ============================================================
# ResumeItem Repository
# ============================================================
class ResumeItemRepository(BaseRepository[ResumeItem]):
    """자소서 문항 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ResumeItem, session)

    async def get_by_question_id(self, question_id: int) -> Sequence[ResumeItem]:
        """
        특정 자소서 세트의 모든 문항을 순서대로 조회한다.

        Args:
            question_id: 자소서 세트 PK

        Returns:
            문항 목록 (order_index 기준 정렬)
        """
        stmt = select(self.model).where(self.model.question_id == question_id).order_by(self.model.order_index.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()


# ============================================================
# ResumeDraft Repository
# ============================================================
class ResumeDraftRepository(BaseRepository[ResumeDraft]):
    """자소서 초안(버전 관리) Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ResumeDraft, session)

    async def get_by_item_id(self, item_id: int) -> Sequence[ResumeDraft]:
        """
        특정 문항의 모든 초안을 버전 순으로 조회한다.

        Args:
            item_id: 문항 PK

        Returns:
            초안 목록 (version 오름차순)
        """
        stmt = select(self.model).where(self.model.item_id == item_id).order_by(self.model.version.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_current_draft(self, item_id: int) -> ResumeDraft | None:
        """
        문항의 현재 활성 초안을 반환한다.

        Args:
            item_id: 문항 PK

        Returns:
            현재 활성 초안 또는 None
        """
        stmt = select(self.model).where(self.model.item_id == item_id, self.model.is_current.is_(True)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_new_version(self, item_id: int, content: str) -> ResumeDraft:
        """
        새 버전의 초안을 생성한다.

        기존 is_current 초안들을 False로 변경하고, 새 초안을 is_current=True로 저장한다.
        버전 번호는 자동으로 증가한다.

        Args:
            item_id: 문항 PK
            content: 초안 본문

        Returns:
            새로 생성된 ResumeDraft
        """
        # 기존 current 초안 해제
        stmt = (
            update(self.model)
            .where(self.model.item_id == item_id, self.model.is_current.is_(True))
            .values(is_current=False)
        )
        await self.session.execute(stmt)

        # 최신 버전 번호 조회
        version_stmt = select(func.coalesce(func.max(self.model.version), 0)).where(self.model.item_id == item_id)
        result = await self.session.execute(version_stmt)
        max_version = result.scalar() or 0

        # 새 초안 생성
        new_draft = await self.create(
            {"item_id": item_id, "content": content, "version": max_version + 1, "is_current": True}
        )

        return new_draft


# ============================================================
# ResumeFeedback Repository
# ============================================================
class ResumeFeedbackRepository(BaseRepository[ResumeFeedback]):
    """AI 코칭 피드백 Repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ResumeFeedback, session)

    async def get_by_draft_id(self, draft_id: int) -> Sequence[ResumeFeedback]:
        """
        특정 초안의 모든 피드백을 조회한다.

        Args:
            draft_id: 초안 PK

        Returns:
            피드백 목록 (최신순)
        """
        stmt = select(self.model).where(self.model.draft_id == draft_id).order_by(self.model.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_by_draft_id(self, draft_id: int) -> ResumeFeedback | None:
        """
        초안의 최신 피드백을 반환한다.

        Args:
            draft_id: 초안 PK

        Returns:
            최신 피드백 또는 None
        """
        stmt = select(self.model).where(self.model.draft_id == draft_id).order_by(self.model.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
