from typing import TYPE_CHECKING

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.common.models.base import Base, TimestampMixin


if TYPE_CHECKING:
    from .analysis_report import AnalysisReport
    from .report_job import ReportJob
    from .talent import CompanyTalent


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    corp_code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True, index=True)  # 고유 번호
    stock_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )  # 상장회사인 경우 주식의 종목 코드
    industry_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # 산업 코드 (※주의 : dart-fss library에는 없고, 홈페이지에는 있음)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 업종
    product: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 주요 제품

    # Relationships (lazy="select" — 명시적 접근 시에만 로드)
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(
        "AnalysisReport", back_populates="company", lazy="select", cascade="all, delete-orphan"
    )
    report_jobs: Mapped[list["ReportJob"]] = relationship(
        "ReportJob", back_populates="company", lazy="select", cascade="all, delete-orphan"
    )
    talents: Mapped[list["CompanyTalent"]] = relationship(
        "CompanyTalent", back_populates="company", lazy="select", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # company_name, corp_code의 unique/index는 mapped_column에서 선언 완료
        Index("idx_company_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Company(name={self.company_name}, code={self.corp_code})>"
