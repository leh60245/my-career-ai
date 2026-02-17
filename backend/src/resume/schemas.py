"""
Resume 도메인 Pydantic Schemas

API 요청/응답 모델 및 서비스 내부 데이터 전달용 DTO.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# ResumeQuestion (자소서 세트)
# ============================================================
class ResumeItemCreate(BaseModel):
    """문항 생성 요청 (세트 내 개별 문항)."""

    type: str = Field(..., description="문항 유형 (MOTIVATION, COMPETENCY, CHALLENGE 등)")
    content: str = Field(..., description="문항 지문")
    max_length: int | None = Field(None, description="최대 글자수")
    order_index: int = Field(default=0, description="문항 순서")


class ResumeQuestionCreate(BaseModel):
    """자소서 세트 생성 요청."""

    company_id: int | None = Field(None, description="지원 기업 ID")
    job_category_id: int | None = Field(None, description="직무 카테고리 ID")
    job_text: str | None = Field(None, description="직접 입력 직무명")
    title: str = Field(..., min_length=1, max_length=500, description="자소서 세트 제목")
    target_season: str | None = Field(None, description="목표 채용 시즌 (e.g., 2026-1H)")
    applicant_type: str = Field(default="NEW", description="지원자 유형 (NEW, EXPERIENCED)")
    items: list[ResumeItemCreate] = Field(default_factory=list, description="문항 목록")


class ResumeItemResponse(BaseModel):
    """문항 응답."""

    id: int
    question_id: int
    type: str
    content: str
    max_length: int | None = None
    order_index: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeQuestionResponse(BaseModel):
    """자소서 세트 응답 (문항 포함)."""

    id: int
    user_id: int
    company_id: int | None = None
    job_category_id: int | None = None
    job_text: str | None = None
    title: str
    target_season: str | None = None
    applicant_type: str = "NEW"
    is_archived: bool
    items: list[ResumeItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeQuestionListItem(BaseModel):
    """자소서 세트 목록 항목 (문항 미포함)."""

    id: int
    user_id: int
    company_id: int | None = None
    title: str
    target_season: str | None = None
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# ResumeDraft (초안)
# ============================================================
class ResumeDraftCreate(BaseModel):
    """초안 생성 요청."""

    content: str = Field(..., min_length=1, description="작성 본문")


class ResumeDraftResponse(BaseModel):
    """초안 응답."""

    id: int
    item_id: int
    content: str
    version: int
    is_current: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# ResumeFeedback (AI 코칭 결과)
# ============================================================
class ResumeFeedbackResponse(BaseModel):
    """AI 피드백 응답."""

    id: int
    draft_id: int
    ai_model: str
    guide_json: dict[str, Any] | None = None
    correction_content: str | None = None
    feedback_points: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Guide Service 요청/응답
# ============================================================
class GuideRequest(BaseModel):
    """작성 가이드 생성 요청."""

    item_id: int = Field(..., description="문항 PK (ResumeItem ID)")
    user_id: int = Field(..., description="사용자 PK")


class GuideResponse(BaseModel):
    """작성 가이드 응답 (LLM 생성 결과)."""

    question_intent: str = Field(..., description="질문 의도 분석")
    keywords: list[str] = Field(default_factory=list, description="핵심 키워드")
    material_guide: str = Field(..., description="소재 선정 가이드")
    writing_points: str = Field(..., description="작성 포인트 (STAR 기법 등)")
    cautions: str = Field(..., description="주의사항")
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Correction Service 요청/응답
# ============================================================
class CorrectionRequest(BaseModel):
    """첨삭 요청."""

    draft_id: int = Field(..., description="초안 PK (ResumeDraft ID)")
    user_id: int = Field(..., description="사용자 PK")


class CorrectionResponse(BaseModel):
    """첨삭 응답 (LLM 생성 결과)."""

    feedback_points: list[dict[str, str]] = Field(
        ..., description="3-Point 피드백 [{category, issue, suggestion}, ...]"
    )
    revised_content: str = Field(..., description="수정된 완성본")
    score: dict[str, int] = Field(..., description="항목별 점수 (logic, job_fit, expression, structure)")
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Draft History (초안 + 피드백 이력)
# ============================================================
class DraftHistoryItem(BaseModel):
    """초안 + 관련 피드백 묶음."""

    draft: ResumeDraftResponse
    feedbacks: list[ResumeFeedbackResponse] = Field(default_factory=list)


class DraftHistoryResponse(BaseModel):
    """특정 문항의 초안/첨삭 히스토리."""

    item_id: int
    history: list[DraftHistoryItem] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
