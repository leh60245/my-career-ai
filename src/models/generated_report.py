from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from src.models import ReportJob


class GeneratedReport(Base, CreatedAtMixin):
    __tablename__ = "generated_reports"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("report_jobs.job_id"), nullable=False)

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 비정규화 (조회 편의)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    toc_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    conversation_log: Mapped[dict[str, Any] | list | None] = mapped_column(JSON, nullable=True)
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(String(50), default="gpt-4o", nullable=False)

    # Relationships
    report_job: Mapped["ReportJob"] = relationship("ReportJob", back_populates="generated_report")
