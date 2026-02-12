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
