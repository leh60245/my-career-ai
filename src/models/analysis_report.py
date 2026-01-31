from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

if TYPE_CHECKING:
    from .company import Company
    from .source_material import SourceMaterial


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)

    report_type: Mapped[str | None] = mapped_column(String(50), default="annual", nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rcept_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    rcept_dt: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="analysis_reports")
    source_materials: Mapped[list["SourceMaterial"]] = relationship(
        "SourceMaterial",
        back_populates="analysis_report",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
