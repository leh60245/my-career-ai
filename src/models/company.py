from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models import AnalysisReport, ReportJob


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

    corp_code: Mapped[str | None] = mapped_column(String(8), nullable=True, unique=True, index=True)  # 고유 번호
    stock_code: Mapped[str | None] = mapped_column(
        String(6), nullable=True, unique=True, index=True
    )  # 상장회사인 경우 주식의 종목 코드
    # induty_code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 산업 코드
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
