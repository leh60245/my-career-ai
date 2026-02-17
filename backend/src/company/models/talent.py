"""
CompanyTalent (인재상) 모델

기업별 인재상 데이터를 관리하는 테이블.
Company 도메인 내부에서 Company와 N:1 관계를 가짐.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.common.models.base import Base, TimestampMixin


if TYPE_CHECKING:
    from .company import Company


class CompanyTalent(Base, TimestampMixin):
    """
    기업 인재상 테이블.

    기업이 공개한 핵심 가치 및 인재상 정보를 연도별로 관리.
    """

    __tablename__ = "company_talents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="기준 연도")
    core_values: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, comment="핵심 가치 리스트 (List[str])")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="인재상 상세 설명")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, comment="출처 URL")

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="talents")
