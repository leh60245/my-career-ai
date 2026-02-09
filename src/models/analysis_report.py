from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common import AnalysisReportStatus
from src.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from src.models import Company, SourceMaterial


class AnalysisReport(Base, CreatedAtMixin):
    __tablename__ = "analysis_reports"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)

    reprt_code: Mapped[str | None] = mapped_column(
        String(20), default="annual", nullable=True
    )  # 1분기보고서:11013 | 반기보고서:11012 | 3분기보고서:11014 | 사업보고서:11011
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rcept_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # 접수번호
    rcept_dt: Mapped[str] = mapped_column(String(20), nullable=False)  # YYYYMMDD 형식
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_type: Mapped[str] = mapped_column(String(50), default="annual", nullable=False)
    status: Mapped[AnalysisReportStatus] = mapped_column(
        String(50), default=AnalysisReportStatus.PENDING, nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="analysis_reports")
    source_materials: Mapped[list["SourceMaterial"]] = relationship(
        "SourceMaterial",
        back_populates="analysis_report",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
