from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportJobResponse(BaseModel):
    # 식별 정보
    job_id: str = Field(..., alias="id", description="작업 고유 ID (UUID)")
    status: str = Field(..., description="현재 상태 (PENDING, PROCESSING, COMPLETED, FAILED)")

    # 요청 정보
    company_name: str = Field(..., description="요청한 회사명")
    topic: str = Field(..., description="요청한 주제")
    error_message: str | None = Field(None, description="실패 시 에러 메시지")
    created_at: datetime = Field(..., description="작업 요청 시각")
    updated_at: datetime | None = Field(None, description="마지막 상태 변경 시각")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "status": "COMPLETED",
                "company_name": "삼성전자",
                "topic": "재무 분석",
                "error_message": None,
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:45:00",
            }
        },
    )


class ReportSummary(BaseModel):
    job_id: str = Field(..., alias="id")
    company_name: str
    topic: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ReportListResponse(BaseModel):
    total: int
    reports: list[ReportSummary]
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# 기업 분석 요청 관련 (구직자 <-> 관리자)
# ============================================================


class CompanyAnalysisRequestCreate(BaseModel):
    """
    기업 분석 요청 생성 시 입력 데이터.

    구직자가 DB에 없는 기업에 대해 분석을 요청할 때 사용.
    """

    company_id: int = Field(..., description="분석을 요청한 기업 ID")
    company_name: str = Field(..., description="기업명")
    topic: str = Field(..., description="분석 주제 (e.g., '채용정보 분석', '기업문화')")

    model_config = ConfigDict(
        json_schema_extra={"example": {"company_id": 1, "company_name": "삼성전자", "topic": "채용정보"}}
    )


class CompanyAnalysisRequestResponse(BaseModel):
    """
    기업 분석 요청의 상세 정보 응답.

    구직자가 조회할 분석 요청 상태 정보.
    """

    job_id: str = Field(..., alias="id", description="요청 ID (UUID)")
    company_id: int = Field(..., description="기업 ID")
    company_name: str = Field(..., description="기업명")
    topic: str = Field(..., description="분석 주제")
    status: str = Field(..., description="현재 상태 (PENDING, PROCESSING, COMPLETED, FAILED, REJECTED)")
    requested_at: datetime | None = Field(None, description="요청 시간")
    approved_at: datetime | None = Field(None, description="승인 시간")
    rejected_at: datetime | None = Field(None, description="반려 시간")
    rejection_reason: str | None = Field(None, description="반려 사유")
    created_at: datetime = Field(..., description="레코드 생성 시간")
    updated_at: datetime | None = Field(None, description="마지막 업데이트 시간")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={"example": {"job_id": "uuid", "status": "PENDING", "company_name": "삼성전자"}},
    )


class AdminAnalysisRequestResponse(BaseModel):
    """
    관리자가 조회하는 분석 요청 항목.

    사용자 정보와 함께 표시하여 관리자가 승인/반려 판단을 도움.
    """

    job_id: str = Field(..., alias="id", description="요청 ID (UUID)")
    user_id: int = Field(..., description="요청한 구직자 user_id")
    company_id: int = Field(..., description="기업 ID")
    company_name: str = Field(..., description="기업명")
    topic: str = Field(..., description="분석 주제")
    status: str = Field(..., description="현재 상태")
    requested_at: datetime | None = Field(None, description="요청 시간")
    created_at: datetime = Field(..., description="레코드 생성 시간")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={"example": {"job_id": "uuid", "user_id": 123, "company_name": "삼성전자"}},
    )


class AdminAnalysisRequestsResponse(BaseModel):
    """
    관리자용: 분석 요청 목록 응답.
    """

    total: int = Field(..., description="대기 중인 요청 총 개수")
    requests: list[AdminAnalysisRequestResponse] = Field(..., description="분석 요청 목록")

    model_config = ConfigDict(from_attributes=True)


class AdminApproveRequest(BaseModel):
    """관리자의 분석 요청 승인 입력."""

    approved_by_user_id: int = Field(..., description="승인한 관리자의 user_id")

    model_config = ConfigDict(json_schema_extra={"example": {"approved_by_user_id": 456}})


class AdminRejectRequest(BaseModel):
    """관리자의 분석 요청 반려 입력."""

    approved_by_user_id: int = Field(..., description="반려한 관리자의 user_id")
    rejection_reason: str = Field(..., description="반려 사유")

    model_config = ConfigDict(
        json_schema_extra={"example": {"approved_by_user_id": 456, "rejection_reason": "기업 정보 없음"}}
    )
