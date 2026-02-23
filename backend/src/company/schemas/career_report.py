"""
Career AI 분석 보고서 JSON 스키마 (Pydantic V2)

역할:
    - LLM이 반환하는 JSON 출력물의 구조를 정의하고 검증합니다.
    - 스키마 불일치 시 ValidationError를 발생시킵니다.
    - wishlist의 JSON 스키마 정의를 코드로 구현합니다.
"""

from pydantic import BaseModel, ConfigDict, Field


class Financials(BaseModel):
    """재무제표 핵심 수치"""

    revenue: str = Field(default="정보 부족 - 추가 조사 필요", description="매출액 (단위 및 기준 연월)")
    operating_profit: str = Field(default="정보 부족 - 추가 조사 필요", description="영업이익 (단위 및 기준 연월)")

    model_config = ConfigDict(from_attributes=True)


class CompanyOverview(BaseModel):
    """기업에 대한 기본적인 정보 및 주요 재무제표 (산업 애널리스트 데이터 기반)"""

    introduction: str = Field(default="정보 부족 - 추가 조사 필요", description="5문장 이내 기업 요약")
    industry: str = Field(default="정보 부족 - 추가 조사 필요", description="직관적인 업종 표기")
    employee_count: str = Field(default="정보 부족 - 추가 조사 필요", description="최근 기준 직원 수 및 기준일")
    location: str = Field(default="정보 부족 - 추가 조사 필요", description="본사 도로명 주소")
    financials: Financials = Field(default_factory=Financials)

    model_config = ConfigDict(from_attributes=True)


class CorporateCulture(BaseModel):
    """핵심가치, 인재상, 조직문화 (수석 취업 지원관 데이터 기반)"""

    core_values: list[str] = Field(default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="핵심가치 목록")
    ideal_candidate: list[str] = Field(
        default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="인재상 목록"
    )
    work_environment: list[str] = Field(
        default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="조직문화 및 특징적인 복리후생 (개조식)"
    )

    model_config = ConfigDict(from_attributes=True)


class SwotAnalysis(BaseModel):
    """대내외 환경 분석 및 전략 (산업 애널리스트 데이터 기반)"""

    strength: list[str] = Field(default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="강점 목록")
    weakness: list[str] = Field(default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="약점 목록")
    opportunity: list[str] = Field(default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="기회 목록")
    threat: list[str] = Field(default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="위협 목록")
    so_strategy: str = Field(default="정보 부족 - 추가 조사 필요", description="강점을 활용한 기회 선점 전략")
    wt_strategy: str = Field(
        default="정보 부족 - 추가 조사 필요", description="약점과 위협을 극복하는 리스크 관리 전략"
    )

    model_config = ConfigDict(from_attributes=True)


class InterviewPreparation(BaseModel):
    """실전 압박 면접 대비 데이터 (실무 면접관 데이터 기반)"""

    recent_issues: list[str] = Field(
        default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="최근 기업이 직면한 부정적 이슈 및 리스크"
    )
    pressure_questions: list[str] = Field(
        default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="리스크 기반 압박 면접 질문 리스트"
    )
    expected_answers: list[str] = Field(
        default_factory=lambda: ["정보 부족 - 추가 조사 필요"], description="질문에 대한 전략적 답변 가이드라인"
    )

    model_config = ConfigDict(from_attributes=True)


class CareerAnalysisReport(BaseModel):
    """
    Career AI 최종 분석 보고서 스키마

    LLM이 반환하는 JSON을 이 모델로 검증합니다.
    4가지 필수 섹션: company_overview, corporate_culture, swot_analysis, interview_preparation
    """

    company_overview: CompanyOverview = Field(default_factory=CompanyOverview)
    corporate_culture: CorporateCulture = Field(default_factory=CorporateCulture)
    swot_analysis: SwotAnalysis = Field(default_factory=SwotAnalysis)
    interview_preparation: InterviewPreparation = Field(default_factory=InterviewPreparation)

    model_config = ConfigDict(from_attributes=True)
