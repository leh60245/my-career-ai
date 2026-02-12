from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GeneratedReportBase(BaseModel):
    """Base schema for GeneratedReport"""

    # Required fields
    company_name: str = Field(..., max_length=255, description="Company name")
    topic: str = Field(..., description="Analysis topic/query")
    report_content: str = Field(..., description="Full Markdown/HTML report")
    # Optional fields
    toc_text: str | None = Field(None, description="Table of contents")
    references_data: dict[str, Any] | None = Field(None, description="URL references")
    conversation_log: dict[str, Any] | list | None = Field(None, description="Agent dialogue")
    meta_info: dict[str, Any] | None = Field(None, description="Processing metadata")
    model_name: str = Field(default="gpt-4o", max_length=50, description="LLM model used")


class GeneratedReportResponse(GeneratedReportBase):
    """Schema for GeneratedReport response (GET response)"""

    id: int
    job_id: str
    created_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "company_name": "삼성전자",
                "topic": "재무 분석",
                "report_content": "# 삼성전자 재무 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 상태\n3. 전망",
                "references_data": {"dart_report_1": {"url": "..."}},
                "conversation_log": {"turns": []},
                "meta_info": {"search_queries": ["삼성전자 재무"]},
                "model_name": "gpt-4o",
                "created_at": "2024-01-15T10:30:00",
            }
        },
    )


class GeneratedReportCreate(GeneratedReportBase):
    """Schema for creating a new GeneratedReport (POST request)"""

    job_id: str = Field(..., description="Foreign key to report_jobs")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "company_name": "삼성전자",
                "topic": "재무 분석",
                "report_content": "# 삼성전자 재무 분석\n\n## 1. 개요\n...",
                "toc_text": "1. 개요\n2. 재무 상태\n3. 전망",
                "references_data": {"dart_report_1": {"url": "...", "content": "..."}},
                "conversation_log": {"turns": [{"role": "user", "content": "..."}]},
                "meta_info": {
                    "search_queries": ["삼성전자 재무", "반도체 시장"],
                    "processing_time": 120.5,
                },
                "model_name": "gpt-4o",
            }
        }
    )


class GeneratedReportUpdate(BaseModel):
    """Schema for updating a GeneratedReport (PATCH request)"""

    report_content: str | None = None
    toc_text: str | None = None
    references_data: dict[str, Any] | None = None
    meta_info: dict[str, Any] | None = None

    model_config = ConfigDict(json_schema_extra={"example": {"report_content": "# Updated Report\n..."}})


class GeneratedReportListItem(BaseModel):
    """Schema for GeneratedReport list item (compact view)"""

    id: int
    job_id: str
    company_name: str
    topic: str
    model_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GenerateReportRequest(BaseModel):
    """
    Schema for report generation request
    클라이언트가 서버에게 리포트 생성을 부탁
    """

    model_config = ConfigDict(json_schema_extra={"example": {"company_name": "SK하이닉스", "topic": "재무 분석"}})
    company_name: str
    topic: str = "종합 분석"
