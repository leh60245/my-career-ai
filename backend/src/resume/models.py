"""
Resume 도메인 모델 (4-Tier 구조)

테이블:
    - resume_questions: 자소서 세트 (기업/직무별 문항 묶음)
    - resume_items: 개별 문항
    - resume_drafts: 작성 본문 버전 관리
    - resume_feedbacks: AI 코칭 결과
"""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.common.enums import ResumeItemType
from src.common.models.base import Base, TimestampMixin


# ============================================================
# ResumeQuestion (자소서 세트)
# ============================================================

class ResumeQuestion(Base, TimestampMixin):
    """
    자소서 세트 테이블.

    사용자가 특정 기업/직무에 대해 작성하는 자소서 문항 묶음.
    company_id와 job_category_id는 선택적 (자유 작성도 가능).
    """

    __tablename__ = "resume_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=True, index=True,
        comment="지원 기업 ID (선택)"
    )
    job_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_categories.id"), nullable=True,
        comment="직무 카테고리 ID (선택)"
    )
    job_text: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="사용자 직접 입력 직무명 (보존용)"
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="자소서 세트 제목"
    )
    target_season: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="목표 채용 시즌 (e.g., 2026-1H)"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="아카이브 여부"
    )

    # Relationships
    items: Mapped[list["ResumeItem"]] = relationship(
        "ResumeItem", back_populates="question", lazy="select",
        cascade="all, delete-orphan", order_by="ResumeItem.order_index"
    )


# ============================================================
# ResumeItem (문항)
# ============================================================

class ResumeItem(Base, TimestampMixin):
    """
    자소서 개별 문항 테이블.

    ResumeQuestion에 속한 각 문항의 지문, 유형, 글자수 제한 등을 관리.
    """

    __tablename__ = "resume_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resume_questions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    type: Mapped[ResumeItemType] = mapped_column(
        Enum(ResumeItemType, name="resume_item_type"),
        nullable=False,
        comment="문항 유형 (지원동기, 직무역량 등)",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="문항 지문"
    )
    max_length: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="최대 글자수 제한"
    )
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="문항 순서"
    )

    # Relationships
    question: Mapped["ResumeQuestion"] = relationship("ResumeQuestion", back_populates="items")
    drafts: Mapped[list["ResumeDraft"]] = relationship(
        "ResumeDraft", back_populates="item", lazy="select",
        cascade="all, delete-orphan", order_by="ResumeDraft.version"
    )


# ============================================================
# ResumeDraft (버전 관리)
# ============================================================

class ResumeDraft(Base, TimestampMixin):
    """
    자소서 작성 본문 버전 관리 테이블.

    각 문항(ResumeItem)에 대해 여러 버전의 작성본을 저장.
    is_current=True인 버전이 현재 활성 버전.
    """

    __tablename__ = "resume_drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resume_items.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="사용자 작성 본문"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="버전 번호 (문항 내 자동 증가)"
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="현재 활성 버전 여부"
    )

    # Relationships
    item: Mapped["ResumeItem"] = relationship("ResumeItem", back_populates="drafts")
    feedbacks: Mapped[list["ResumeFeedback"]] = relationship(
        "ResumeFeedback", back_populates="draft", lazy="select",
        cascade="all, delete-orphan"
    )


# ============================================================
# ResumeFeedback (AI 코칭 결과)
# ============================================================

class ResumeFeedback(Base, TimestampMixin):
    """
    AI 코칭 피드백 테이블.

    자소서 초안(Draft)에 대한 AI 분석 결과를 저장.
    작성 가이드, 첨삭 내용, 3-Point 피드백, 항목별 점수를 포함.
    """

    __tablename__ = "resume_feedbacks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resume_drafts.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    ai_model: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="사용된 AI 모델명"
    )
    guide_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="작성 가이드 데이터"
    )
    correction_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="첨삭 완성본 (코칭 결과)"
    )
    feedback_points: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="3-Point 피드백 (강점, 보완점, 제안)"
    )
    score: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="항목별 점수"
    )

    # Relationships
    draft: Mapped["ResumeDraft"] = relationship("ResumeDraft", back_populates="feedbacks")
