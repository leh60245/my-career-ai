from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.common.enums import ReportJobStatus
from backend.src.common.models.base import Base, TimestampMixin


if TYPE_CHECKING:
    from backend.src.company.models.company import Company
    from backend.src.company.models.generated_report import GeneratedReport
    from backend.src.user.models import User


class ReportJob(Base, TimestampMixin):
    """
    기업 분석 요청 및 생성 작업 기록.

    사용자의 요청 → 관리자 승인 → AI 분석 실행 → 완료/반려의 전체 라이프사이클을 추적.
    """

    __tablename__ = "report_jobs"

    # Primary Key & Basic Fields
    id: Mapped[str] = mapped_column("job_id", String, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)

    # Job Status & Error Handling
    status: Mapped[ReportJobStatus] = mapped_column(
        String, default=ReportJobStatus.PENDING.value
    )  # PENDING, PROCESSING, COMPLETED, FAILED, REJECTED
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    # Request & Approval Tracking
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="분석을 요청한 구직자의 user_id"
    )
    requested_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="요청 시간 (TimestampMixin의 created_at과 별개로 추적)"
    )

    # Approval & Rejection
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="승인한 관리자의 user_id"
    )
    approved_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="승인 시간")

    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="반려 사유 (REJECTED 상태일 때만 입력)"
    )
    rejected_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="반려 시간")

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="report_jobs")
    requester: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="select")
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by], lazy="select")
    generated_report: Mapped["GeneratedReport | None"] = relationship(
        "GeneratedReport", back_populates="report_job", uselist=False
    )
