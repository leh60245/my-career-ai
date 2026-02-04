from pydantic import BaseModel, ConfigDict


class GenerateReportRequest(BaseModel):
    """
    Schema for report generation request
    클라이언트가 서버에게 리포트 생성을 부탁
    """

    model_config = ConfigDict(json_schema_extra={"example": {"company_name": "SK하이닉스", "topic": "재무 분석"}})
    company_name: str
    topic: str = "종합 분석"
