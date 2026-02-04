from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportJobResponse(BaseModel):
    # 식별 정보
    job_id: str = Field(..., description="작업 고유 ID (UUID)")
    status: str = Field(..., description="현재 상태 (PENDING, PROCESSING, COMPLETED, FAILED)")

    # 요청 정보
    company_name: str = Field(..., description="요청한 회사명")
    topic: str = Field(..., description="요청한 주제")
    created_at: datetime = Field(..., description="작업 요청 시각")
    updated_at: datetime | None = Field(None, description="마지막 상태 변경 시각 (완료/실패 시각)")
    result_report_id: int | None = Field(None, description="생성된 리포트의 ID (완료 시)")
    user_message: str | None = Field(None, description="작업 진행 중 사용자에게 보낼 메시지")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "job_id": "job-1234-5678",
                "status": "COMPLETED",
                "company_name": "삼성전자",
                "topic": "재무 분석",
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T10:45:00",
                "result_report_id": 1,
                "user_message": "작업이 성공적으로 완료되었습니다.",
            }
        },
    )


class ReportSummary(BaseModel):
    job_id: str
    report_id: int | None = None
    company_name: str
    topic: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ReportListResponse(BaseModel):
    total: int
    reports: list[ReportSummary]
