"""
User 도메인 Pydantic Schemas

사용자 계정 및 프로필 관련 API 요청/응답 모델.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ============================================================
# User (계정)
# ============================================================
class UserResponse(BaseModel):
    """사용자 계정 응답."""

    id: int
    email: str
    role: str
    tier: str
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# JobSeekerProfile (구직자 프로필)
# ============================================================
class JobSeekerProfileResponse(BaseModel):
    """구직자 프로필 응답."""

    user_id: int
    affiliation_id: int | None = None
    student_id: str | None = None
    education: dict[str, Any] | None = None
    specs: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobSeekerProfileUpdate(BaseModel):
    """구직자 프로필 수정 요청."""

    student_id: str | None = None
    education: dict[str, Any] | None = None
    specs: dict[str, Any] | None = None


# ============================================================
# 통합 응답 (User + Profile)
# ============================================================
class UserMeResponse(BaseModel):
    """현재 사용자 정보 응답 (프로필 포함)."""

    user: UserResponse
    job_seeker_profile: JobSeekerProfileResponse | None = None


# ============================================================
# User 생성 (임시 — 향후 Auth 도메인으로 이동 예정)
# ============================================================
class UserCreate(BaseModel):
    """사용자 생성 요청 (개발/테스트용)."""

    email: EmailStr = Field(..., description="이메일 주소")
    role: str = Field(default="JOB_SEEKER", description="사용자 역할")
