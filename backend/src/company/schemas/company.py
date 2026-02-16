from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompanyCreate(BaseModel):
    """
    Request schema for creating a new company.

    POST /api/companies
    """

    company_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Official company name (required)",
    )

    corp_code: str | None = Field(None, max_length=20, description="6-digit DART corporation code")

    stock_code: str | None = Field(None, max_length=20, description="6-digit Korea Exchange stock code")

    industry_code: str | None = Field(None, max_length=100, description="Industry classification code")
    sector: str | None = Field(None, max_length=100, description="Business sector")
    product: str | None = Field(None, max_length=255, description="Main products/services")

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        """Ensure company name is not empty after strip."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_name": "삼성전자",
                "corp_code": "005930",
                "stock_code": "005930",
                "sector": "Semiconductor",
            }
        },
    )


class CompanyUpdate(BaseModel):
    """
    Request schema for updating a company.

    PATCH /api/companies/{id}
    """

    company_name: str | None = Field(None, min_length=1, max_length=255, description="Official company name")

    corp_code: str | None = Field(None, max_length=20, description="DART corporation code")

    stock_code: str | None = Field(None, max_length=20, description="Korea Exchange stock code")

    industry_code: str | None = Field(None, max_length=100, description="Industry classification code")
    sector: str | None = Field(None, max_length=100, description="Business sector")
    product: str | None = Field(None, max_length=255, description="Main products/services")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "company_name": "삼성전자",
                "corp_code": "005930",
                "stock_code": "005930",
                "sector": "Semiconductor",
            }
        },
    )

class CompanyResponse(BaseModel):
    """
    Response schema for company API endpoints.
    """

    id: int = Field(..., description="Unique company ID")

    company_name: str = Field(..., description="Official company name")

    corp_code: str | None = Field(None, description="DART corporation code")

    stock_code: str | None = Field(None, description="Korea Exchange stock code")

    industry_code: str | None = Field(None, description="Industry classification code")
    sector: str | None = Field(None, description="Business sector")
    product: str | None = Field(None, description="Main products/services")

    created_at: datetime = Field(..., description="Creation timestamp")
    """UTC timestamp of record creation"""

    updated_at: datetime | None = Field(None, description="Last update timestamp")
    """UTC timestamp of last modification"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "company_name": "삼성전자",
                "corp_code": "005930",
                "stock_code": "005930",
                "sector": "Semiconductor",
                "created_at": "2026-01-15T08:30:00+00:00",
                "updated_at": "2026-01-21T10:45:30+00:00",
            }
        },
    )


__all__ = [
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyResponse",
]
