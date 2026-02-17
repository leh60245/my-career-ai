"""
User & Affiliation 도메인 모델

테이블:
    - affiliations: 소속 마스터 (대학, 공공기관, 기업 등)
    - users: 통합 계정
    - job_seeker_profiles: 구직자 상세 프로필
    - manager_profiles: 관리자 상세 프로필
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.common.enums import AffiliationType, UserRole, UserTier
from backend.src.common.models.base import Base, TimestampMixin


if TYPE_CHECKING:
    pass


# ============================================================
# Affiliation (소속 마스터)
# ============================================================


class Affiliation(Base, TimestampMixin):
    """
    소속 기관 마스터 테이블.

    B2B/B2G 확장을 위한 Multi-Tenancy 기반 소속 관리.
    예: 서울대학교, 강남구청, 삼성전자 등
    """

    __tablename__ = "affiliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="소속 기관명")
    type: Mapped[AffiliationType] = mapped_column(
        Enum(AffiliationType, name="affiliation_type"),
        nullable=False,
        comment="소속 유형 (UNIVERSITY, GOVERNMENT, COMPANY, ETC)",
    )
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="이메일 도메인 (e.g., snu.ac.kr)")

    # Relationships
    job_seeker_profiles: Mapped[list["JobSeekerProfile"]] = relationship(
        "JobSeekerProfile", back_populates="affiliation", lazy="select"
    )
    manager_profiles: Mapped[list["ManagerProfile"]] = relationship(
        "ManagerProfile", back_populates="affiliation", lazy="select"
    )


# ============================================================
# User (통합 계정)
# ============================================================


class User(Base, TimestampMixin):
    """
    통합 사용자 계정 테이블.

    role에 따라 job_seeker_profile 또는 manager_profile과 1:1 관계를 가짐.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False, comment="이메일 (로그인 ID)"
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.JOB_SEEKER, comment="사용자 역할"
    )
    tier: Mapped[UserTier] = mapped_column(
        Enum(UserTier, name="user_tier"), nullable=False, default=UserTier.FREE, comment="구독 등급"
    )
    last_login: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True, comment="마지막 로그인 시각")

    # Relationships (1:1)
    job_seeker_profile: Mapped["JobSeekerProfile | None"] = relationship(
        "JobSeekerProfile", back_populates="user", uselist=False, lazy="select", cascade="all, delete-orphan"
    )
    manager_profile: Mapped["ManagerProfile | None"] = relationship(
        "ManagerProfile", back_populates="user", uselist=False, lazy="select", cascade="all, delete-orphan"
    )


# ============================================================
# JobSeekerProfile (구직자 상세)
# ============================================================


class JobSeekerProfile(Base, TimestampMixin):
    """
    구직자 상세 프로필.

    user_id를 PK로 사용하여 User와 1:1 관계.
    소속(Affiliation)이 없는 일반인은 affiliation_id가 Null.
    """

    __tablename__ = "job_seeker_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    affiliation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("affiliations.id"), nullable=True, comment="소속 ID (비소속 시 Null)"
    )
    student_id: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="학번 (해당 시)")
    education: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="학력 정보 (학교, 전공, 상태)"
    )
    specs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="스펙 정보 (어학, 자격증, 경력)")

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="job_seeker_profile")
    affiliation: Mapped["Affiliation | None"] = relationship("Affiliation", back_populates="job_seeker_profiles")


# ============================================================
# ManagerProfile (관리자 상세)
# ============================================================


class ManagerProfile(Base, TimestampMixin):
    """
    관리자 상세 프로필.

    관리자는 반드시 소속(Affiliation)이 있어야 함.
    """

    __tablename__ = "manager_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    affiliation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("affiliations.id"), nullable=False, comment="소속 ID (관리자는 필수)"
    )
    department: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="부서명")

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="manager_profile")
    affiliation: Mapped["Affiliation"] = relationship("Affiliation", back_populates="manager_profiles")
