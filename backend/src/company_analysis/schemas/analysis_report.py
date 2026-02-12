from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnalysisReportBase(BaseModel):
    """Base schema for AnalysisReport (shared fields)"""

    title: str = Field(..., max_length=500, description="Report title")
    rcept_no: str = Field(..., max_length=20, description="DART receipt number (unique)")
    rcept_dt: str = Field(..., max_length=10, description="Receipt date (YYYYMMDD)")
    report_type: str = Field(default="annual", max_length=50, description="Report type")
    status: str = Field(default="PENDING", max_length=50, description="Processing status")


class AnalysisReportCreate(AnalysisReportBase):
    """Schema for creating a new AnalysisReport (POST request)"""

    company_id: int = Field(..., description="Foreign key to companies table")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_id": 1,
                "title": "삼성전자 제60기 사업보고서",
                "rcept_no": "20240101000001",
                "rcept_dt": "20240101",
                "report_type": "annual",
                "status": "PENDING",
            }
        }
    )


class AnalysisReportUpdate(BaseModel):
    """Schema for updating an AnalysisReport (PATCH request)"""

    title: str | None = Field(None, max_length=500)
    report_type: str | None = Field(None, max_length=50)
    status: str | None = Field(None, max_length=50)

    model_config = ConfigDict(json_schema_extra={"example": {"status": "COMPLETED"}})


class AnalysisReportResponse(AnalysisReportBase):
    """Schema for AnalysisReport response (GET response)"""

    id: int
    company_id: int
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "company_id": 1,
                "title": "삼성전자 제60기 사업보고서",
                "rcept_no": "20240101000001",
                "rcept_dt": "20240101",
                "report_type": "annual",
                "status": "COMPLETED",
                "created_at": "2024-01-15T10:30:00",
            }
        },
    )


class AnalysisReportListItem(BaseModel):
    """Schema for AnalysisReport list item (compact view)"""

    id: int
    company_id: int
    title: str
    rcept_no: str
    rcept_dt: str
    report_type: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
