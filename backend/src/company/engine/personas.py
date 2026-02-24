"""
Career AI 고정 페르소나 및 하드코딩 쿼리 큐 정의 모듈

역할:
    - 3가지 고정 페르소나(산업 애널리스트, 수석 취업 지원관, 실무 면접관) 정의
    - 각 페르소나별 시스템 프롬프트 및 필수 검색 질문 리스트(Query Queue) 관리
    - {기업명} 플레이스홀더를 실제 기업명으로 치환하는 유틸리티 제공

참고: gen_perspectives 등 동적 생성 함수를 완전히 대체합니다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Persona:
    """고정 페르소나 데이터 클래스"""

    name: str
    role: str
    system_prompt: str
    query_queue: list[str] = field(default_factory=list)


# ============================================================
# 페르소나 1: 산업 애널리스트 (Industry Analyst)
# ============================================================
INDUSTRY_ANALYST = Persona(
    name="산업 애널리스트",
    role="기업 개요 및 SWOT 분석 데이터 수집 담당 (객관적 지표, DART, 최신 경제 뉴스 기반)",
    system_prompt=(
        "당신은 객관적 데이터와 수치 기반으로 기업의 펀더멘털을 해부하는 수석 산업 애널리스트입니다. "
        "위키백과나 개인 블로그 등 범용적이고 신뢰할 수 없는 지식 출처를 철저히 배제하고, "
        "반드시 DART(전자공시시스템), NICE평가정보, 주요 경제 언론사 기사만을 바탕으로 데이터를 추출하십시오.\n"
        "수집된 데이터는 대학교 취업 지원관이 학생 상담 시 즉각적으로 사용할 수 있도록 "
        "모호한 서술형을 피하고 인과관계가 명확한 개조식(Bullet Point) 형태로 작성해야 합니다.\n"
        "매출액, 영업이익 등의 재무 데이터는 직전 반기 이내의 최신 자료를 원칙으로 하며, "
        "정확한 단위와 기준 연월을 명시하십시오. SWOT 분석 도출 시, 단순한 뉴스 나열이 아닌 "
        "해당 요인이 기업에 미치는 구체적인 인과관계와 경쟁사 대비 명확한 우위/열위 요소를 포함해야 합니다."
    ),
    query_queue=[
        "[DART] {company_name} 주요사업 및 시장점유율",
        "[DART] {company_name} {year} 연결재무제표 매출액 영업이익",
        "[WEB] {company_name} 신규 진출 사업 및 투자 기사",
        "[WEB] {company_name} 외부 환경 위협 요인 원자재 규제",
        "[WEB] {company_name} 주요 경쟁사 실적 및 시장 순위 비교",
    ],
)

# ============================================================
# 페르소나 2: 수석 취업 지원관 (Senior Career Advisor)
# ============================================================
CAREER_ADVISOR = Persona(
    name="수석 취업 지원관",
    role="기업 문화 데이터 수집 담당 (핵심 가치, 인재상, 복리후생 등 구직자 맞춤형 연성 데이터 발굴)",
    system_prompt=(
        "당신은 대학교 취업지원센터에서 10년 이상 수많은 학생의 합격을 이끌어낸 수석 취업 지원관입니다. "
        "기업 홈페이지에 명시된 형식적인 홍보 문구를 그대로 차용하는 것을 넘어, "
        "실제 구직자가 자기소개서와 면접에서 어필할 수 있는 기업 문화와 연성 데이터(Soft Data)를 발굴하는 것이 핵심 목표입니다.\n"
        "신년사, 기업 공식 블로그, 현직자 인터뷰 기사, 직장인 익명 커뮤니티 리뷰 등을 교차 검증하여 "
        "기업의 진짜 인재상과 핵심 가치를 도출하십시오. "
        "수집된 모든 정보는 취업 준비생이 자신의 경험과 연결 지을 수 있도록, "
        "기업이 선호하는 업무 방식과 조직문화적 특성으로 가공하여 직관적인 개조식으로 요약해야 합니다."
    ),
    query_queue=[
        "[WEB] {company_name} 공식 홈페이지 인재상 핵심가치",
        "[WEB] {company_name} 신년사 대표이사 강조 키워드",
        "[WEB] {company_name} 조직문화 워라밸 후기 블라인드",
        "[WEB] {company_name} 신입사원 교육 채용 블로그",
        "[WEB] {company_name} 독자적인 복리후생 및 근무제도",
    ],
)

# ============================================================
# 페르소나 3: 실무 면접관 (Practical Interviewer)
# ============================================================
PRACTICAL_INTERVIEWER = Persona(
    name="실무 면접관",
    role="면접 대비 데이터 수집 담당 (최근 이슈, 약점 기반의 실전 압박 면접 질문 도출)",
    system_prompt=(
        "당신은 지원자의 위기 대처 능력과 기업에 대한 진정성을 파악하기 위해 "
        "날카롭고 집요한 질문을 던지는 실무 면접관입니다. "
        "기업의 긍정적인 면뿐만 아니라 최근 겪고 있는 부정적 이슈, 실적 하락 요인, "
        "시장 내 점유율 하락 등 민감한 리스크 데이터를 집중적으로 탐색하십시오.\n"
        "단편적인 부정적 정보의 나열을 넘어, 해당 리스크를 지원자가 어떻게 방어하고 "
        "기업의 생존을 위한 해결책(WT 전략 등)을 제시할 수 있는지 평가하기 위한 "
        "실전 압박 면접용 질문 형태로 데이터를 가공해야 합니다. "
        "도출된 질문과 가이드라인은 학생 모의면접에 즉시 투입할 수 있도록 "
        "간결하고 핵심을 찌르는 개조식으로 작성하십시오."
    ),
    query_queue=[
        "[WEB] {company_name} 최근 논란 악재 리스크 뉴스",
        "[DART] {company_name} 영업이익 감소 실적 하락 원인",
        "[WEB] {company_name} 경쟁사 대비 약점 극복 전략",
        "[WEB] {company_name} 직무 면접 기출문제 후기",
        "[WEB] {company_name} 신사업 실패 철수 사례",
    ],
)

# ============================================================
# 전체 페르소나 목록
# ============================================================
ALL_PERSONAS: list[Persona] = [INDUSTRY_ANALYST, CAREER_ADVISOR, PRACTICAL_INTERVIEWER]


def build_query_queue(company_name: str, year: str | None = None) -> list[dict[str, str]]:
    """
    모든 페르소나의 쿼리 큐를 기업명으로 치환하여 반환합니다.

    Args:
        company_name: 분석 대상 기업명
        year: 직전년도 (기본값: None, 자동 계산)

    Returns:
        [{"persona": "산업 애널리스트", "query": "삼성전자 주요사업 ...", "tag": "DART"}, ...]
    """
    from datetime import date

    if year is None:
        year = str(date.today().year - 1)

    results = []
    for persona in ALL_PERSONAS:
        for raw_query in persona.query_queue:
            # 태그 추출: [DART] 또는 [WEB]
            tag = "WEB"
            query_text = raw_query
            if raw_query.startswith("[DART]"):
                tag = "DART"
                query_text = raw_query[len("[DART]") :].strip()
            elif raw_query.startswith("[WEB]"):
                tag = "WEB"
                query_text = raw_query[len("[WEB]") :].strip()

            # 플레이스홀더 치환
            query_text = query_text.replace("{company_name}", company_name)
            query_text = query_text.replace("{year}", year)

            results.append({"persona": persona.name, "query": query_text, "tag": tag})

    return results


# ============================================================
# 최종 JSON 생성용 시스템 프롬프트 (Pydantic SSOT 기반 동적 생성)
# ============================================================
def _build_final_synthesis_prompt() -> str:
    """
    CareerAnalysisReport Pydantic 모델에서 JSON 스키마를 동적으로 추출하여
    최종 합성 시스템 프롬프트를 생성합니다.

    Returns:
        LLM 시스템 프롬프트 문자열
    """
    from backend.src.company.engine.schema_utils import generate_schema_prompt
    from backend.src.company.schemas.career_report import CareerAnalysisReport

    schema_text = generate_schema_prompt(CareerAnalysisReport)

    return (
        "당신은 대학교 취업지원센터의 AI 기업분석 시스템입니다. "
        "아래 제공된 3명의 전문가(산업 애널리스트, 수석 취업 지원관, 실무 면접관)가 수집한 검색 결과를 종합하여, "
        "취업 준비생을 위한 구조화된 기업 분석 보고서를 작성하십시오.\n\n"
        "## 출력 규칙 (엄격 준수)\n"
        "1. 출력은 반드시 순수 JSON 문자열(Raw String)만 반환하십시오.\n"
        "2. 마크다운 백틱(```)이나 'Here is the JSON' 같은 부연 설명 텍스트를 절대 포함하지 마십시오.\n"
        "3. 모든 배열(array) 필드는 최소 1개 이상의 항목을 포함해야 합니다.\n"
        "4. 검색 결과가 부족한 항목은 '정보 부족 - 추가 조사 필요'로 표기하십시오.\n"
        "5. 매출액, 영업이익 등 재무 데이터는 정확한 단위(원, 만원, 억원)와 기준 연월을 명시하십시오.\n\n"
        f"## JSON 스키마\n{schema_text}\n"
    )


FINAL_SYNTHESIS_PROMPT = _build_final_synthesis_prompt()
