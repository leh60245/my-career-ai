"""
JobCategory (직무 카테고리) 공통 모델

전체 도메인에서 참조하는 직무 분류 마스터 테이블.
Self-referencing으로 계층 구조를 지원함.
"""

from sqlalchemy import ARRAY, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.common.models.base import Base, TimestampMixin


class JobCategory(Base, TimestampMixin):
    """
    직무 카테고리 마스터 테이블.

    계층형(Self-referencing) 구조로 대분류-소분류 관리.
    예: 마케팅 > 디지털마케팅, IT > 백엔드개발
    """

    __tablename__ = "job_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="직무 카테고리명 (e.g., 마케팅)"
    )
    keywords: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, comment="핵심 역량 키워드 리스트"
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_categories.id"), nullable=True, comment="상위 카테고리 ID (Self-referencing)"
    )

    # Relationships (Self-referencing)
    parent: Mapped["JobCategory | None"] = relationship(
        "JobCategory", remote_side="JobCategory.id", back_populates="children", lazy="select"
    )
    children: Mapped[list["JobCategory"]] = relationship(
        "JobCategory", back_populates="parent", lazy="select"
    )
