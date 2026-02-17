from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.common.enums import ReportJobStatus
from backend.src.common.models.base import Base, TimestampMixin


if TYPE_CHECKING:
    from .company import Company
    from .generated_report import GeneratedReport


class ReportJob(Base, TimestampMixin):
    __tablename__ = "report_jobs"

    # Fields
    id: Mapped[str] = mapped_column("job_id", String, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)

    status: Mapped[ReportJobStatus] = mapped_column(
        String, default=ReportJobStatus.PENDING.value
    )  # PENDING, PROCESSING, COMPLETED, FAILED
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)

    # error message if any
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="report_jobs")
    generated_report: Mapped["GeneratedReport | None"] = relationship(
        "GeneratedReport", back_populates="report_job", uselist=False
    )
