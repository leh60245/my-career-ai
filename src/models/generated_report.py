from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

if TYPE_CHECKING:
    from .report_job import ReportJob


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("report_jobs.job_id"), nullable=False)

    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    toc_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    conversation_log: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(50), default="gpt-4o", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    # Relationships
    report_job: Mapped["ReportJob"] = relationship("ReportJob", back_populates="generated_report")
