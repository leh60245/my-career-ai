from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .analysis_report import AnalysisReport
    from .report_job import ReportJob


class Company(
    Base,
    TimestampMixin,
):
    __tablename__ = "companies"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    corp_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    stock_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(
        "AnalysisReport", back_populates="company", lazy="selectin", cascade="all, delete-orphan"
    )
    report_jobs: Mapped[list["ReportJob"]] = relationship(
        "ReportJob", back_populates="company", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("company_name", name="uq_company_name"),
        Index("idx_company_corp_code", "corp_code"),
        Index("idx_company_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Company(id={self.id}, name={self.company_name!r}, corp_code={self.corp_code!r})>"
