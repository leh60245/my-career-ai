from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

if TYPE_CHECKING:
    from .company import Company
    from .generated_report import GeneratedReport


class ReportJob(Base):
    __tablename__ = "report_jobs"

    # Fields
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)

    status: Mapped[str] = mapped_column(String, default="PENDING")  # PENDING, PROCESSING, COMPLETED, FAILED
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now(), nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="report_jobs")
    generated_report: Mapped["GeneratedReport | None"] = relationship(
        "GeneratedReport",
        back_populates="report_job",
        uselist=False,
    )
