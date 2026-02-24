"""
NLI 기반 팩트체크 Evaluator (심사관 에이전트)

역할:
    - 1차 생성된 JSON 초안의 문장들이 원천 데이터(Source Context)에
      명확히 근거하는지 NLI(자연어 추론) 관점에서 검증합니다.
    - 특히 swot_analysis, interview_preparation 섹션을 집중 검증합니다.
    - 환각(Hallucination)이 의심되는 항목을 구조화된 JSON 배열로 반환합니다.

출력 스키마:
    List[HallucinationFinding] 형태로, 각 항목에는 섹션명, 문제의 문장,
    원천 데이터 부재 사유, 수정 지침이 포함됩니다.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.src.common.config import AI_CONFIG


logger = logging.getLogger(__name__)


# ============================================================
# Pydantic 출력 스키마
# ============================================================


class HallucinationFinding(BaseModel):
    """환각이 의심되는 개별 항목"""

    section: str = Field(description="환각이 발견된 섹션명 (예: swot_analysis.strength)")
    statement: str = Field(description="환각이 의심되는 원문 문장")
    reason: str = Field(description="원천 데이터에서 근거를 찾을 수 없는 사유")
    instruction: str = Field(description="수정 지침 (rewrite: 재작성, delete: 삭제)")

    model_config = ConfigDict(from_attributes=True)


class EvaluationResult(BaseModel):
    """Evaluator의 전체 평가 결과"""

    has_hallucination: bool = Field(description="환각 존재 여부")
    findings: list[HallucinationFinding] = Field(default_factory=list, description="환각이 의심되는 항목 리스트")
    summary: str = Field(default="", description="전체 평가 요약")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Evaluator 시스템 프롬프트 (Pydantic SSOT 기반 동적 생성)
# ============================================================

# 무의미한 기호 필터링 패턴: 이 패턴들만으로 채워진 필드는 정보 없음으로 간주합니다.
MEANINGLESS_PATTERNS = frozenset({"-", "--", "---", "N/A", "n/a", "없음", "해당 없음", ""})


def _build_evaluator_system_prompt() -> str:
    """
    EvaluationResult Pydantic 모델에서 JSON 스키마를 동적으로 추출하여
    Evaluator 시스템 프롬프트를 생성합니다.

    Returns:
        Evaluator 시스템 프롬프트 문자열
    """
    from backend.src.company.engine.schema_utils import generate_evaluation_schema_prompt

    schema_text = generate_evaluation_schema_prompt(EvaluationResult)

    return (
        "당신은 AI가 생성한 기업 분석 보고서의 사실 검증을 전담하는 NLI(자연어 추론) 기반 팩트체크 심사관입니다.\n\n"
        "## 핵심 임무\n"
        "주어진 JSON 초안의 문장들이 검색된 원천 데이터(Source Context)에 명확히 근거하는지 검증하십시오.\n"
        "특히 다음 섹션을 집중적으로 검증해야 합니다:\n"
        "- swot_analysis: 강점/약점/기회/위협 및 전략 (so_strategy, wt_strategy)\n"
        "- interview_preparation: 최근 이슈, 압박 면접 질문, 전략적 답변 가이드\n\n"
        "## 판정 기준 (NLI 3단계)\n"
        "1. **Entailment (수반)**: 원천 데이터에서 해당 문장을 논리적으로 도출할 수 있음 -> 통과\n"
        "2. **Neutral (중립)**: 원천 데이터와 직접적 관련이 없으나, 일반 상식 수준에서 허용 가능 -> 통과\n"
        "3. **Contradiction (모순/무근거)**: 원천 데이터에 반하거나, 전혀 근거를 찾을 수 없는 구체적 수치/사실/고유명사 포함 -> 환각 판정\n\n"
        "## 환각 판정 세부 규칙\n"
        "- 원천 데이터에 없는 구체적 수치(매출액, 점유율 등)가 포함된 문장은 환각으로 판정합니다.\n"
        "- 원천 데이터에 없는 고유명사(회사명, 인물명, 제품명 등)가 핵심 논거로 사용된 경우 환각으로 판정합니다.\n"
        "- '정보 부족 - 추가 조사 필요'라고 표기된 항목은 검증 대상에서 제외합니다.\n"
        "- 하이픈('-'), 'N/A' 등 무의미한 기호만으로 채워진 필드는 검증 대상에서 제외합니다.\n"
        "- 일반적 상식이나 업계 통념 수준의 서술(예: '경쟁이 심화되고 있다')은 환각으로 판정하지 않습니다.\n\n"
        "## 출력 규칙 (엄격 준수)\n"
        "1. 출력은 반드시 순수 JSON 문자열만 반환하십시오.\n"
        "2. 마크다운 백틱(```)이나 부연 설명 텍스트를 절대 포함하지 마십시오.\n"
        "3. instruction 필드 값은 반드시 'rewrite' 또는 'delete' 중 하나여야 합니다.\n"
        "   - rewrite: 원천 데이터에 부분적 근거가 있어 재작성으로 교정 가능한 경우\n"
        "   - delete: 원천 데이터에 근거가 전혀 없어 삭제해야 하는 경우\n\n"
        f"## JSON 출력 스키마\n{schema_text}\n"
    )


EVALUATOR_SYSTEM_PROMPT = _build_evaluator_system_prompt()


def _is_meaningless_value(value: str) -> bool:
    """
    필드 값이 무의미한 기호(하이픈 등)로만 채워져 있는지 판별합니다.

    Args:
        value: 검사할 문자열

    Returns:
        무의미한 값이면 True
    """
    stripped = value.strip()
    return stripped in MEANINGLESS_PATTERNS


# ============================================================
# Evaluator 핵심 로직
# ============================================================


def _build_evaluation_prompt(draft_json: str, source_context: str, company_name: str) -> str:
    """
    Evaluator에게 전달할 사용자 프롬프트를 구성합니다.

    Args:
        draft_json: 1차 생성된 JSON 초안 (문자열)
        source_context: 원천 검색 데이터 컨텍스트
        company_name: 분석 대상 기업명

    Returns:
        Evaluator 사용자 프롬프트
    """
    return (
        f"## 검증 대상 기업: {company_name}\n\n"
        f"## 1차 생성된 JSON 초안 (검증 대상)\n"
        f"```json\n{draft_json}\n```\n\n"
        f"## 원천 데이터 (Source Context)\n"
        f"아래는 검색 엔진을 통해 수집된 원천 데이터입니다. "
        f"JSON 초안의 각 문장이 이 원천 데이터에 근거하는지 NLI 관점에서 검증하십시오.\n\n"
        f"{source_context}\n\n"
        f"위 원천 데이터를 기반으로 JSON 초안의 환각 여부를 판정하고, "
        f"결과를 지정된 JSON 스키마로 반환하십시오."
    )


async def evaluate_report(
    draft_json: str, source_context: str, company_name: str, model_provider: str = "openai"
) -> EvaluationResult:
    """
    1차 생성된 JSON 초안을 NLI 기반으로 팩트체크합니다.

    Args:
        draft_json: 1차 생성된 JSON 리포트 (문자열)
        source_context: 원천 검색 데이터 컨텍스트
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더 ('openai' 또는 'gemini')

    Returns:
        EvaluationResult: 환각 탐지 결과
    """
    import asyncio

    import litellm

    user_prompt = _build_evaluation_prompt(draft_json, source_context, company_name)

    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key")
    else:
        model = "gpt-4o"
        api_key = AI_CONFIG.get("openai_api_key")

    if not api_key:
        raise ValueError(f"{model_provider} API 키가 설정되지 않았습니다.")

    messages = [{"role": "system", "content": EVALUATOR_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: litellm.completion(
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"},
        ),
    )

    content = response.choices[0].message.content  # type: ignore[union-attr]
    if content is None:
        raise ValueError("Evaluator LLM이 빈 응답을 반환했습니다.")

    return _parse_evaluation_result(content)


def _parse_evaluation_result(raw_text: str) -> EvaluationResult:
    """
    Evaluator LLM 응답을 EvaluationResult로 파싱합니다.

    Args:
        raw_text: LLM 응답 텍스트

    Returns:
        EvaluationResult 객체

    Raises:
        ValueError: 파싱 실패 시
    """
    from backend.src.company.engine.json_utils import extract_json_string

    try:
        json_str = extract_json_string(raw_text)
        data = json.loads(json_str)
        return EvaluationResult.model_validate(data)
    except Exception as e:
        logger.error(f"Evaluator 응답 파싱 실패: {e}")
        # 파싱 실패 시 환각 없음으로 처리 (안전 측 판단)
        return EvaluationResult(
            has_hallucination=False, findings=[], summary=f"Evaluator 응답 파싱 실패로 검증 건너뜀: {e}"
        )


def extract_sections_for_evaluation(report_dict: dict[str, Any]) -> dict[str, list[str]]:
    """
    JSON 리포트에서 검증 대상 섹션의 문장들을 추출합니다.
    주로 swot_analysis, interview_preparation 섹션을 대상으로 합니다.

    필터링 규칙:
        - '정보 부족' 기본값 필드 제외
        - 하이픈('-'), 'N/A' 등 무의미한 기호만으로 채워진 필드 제외

    Args:
        report_dict: 리포트 딕셔너리

    Returns:
        섹션별 문장 리스트 (예: {"swot_analysis.strength": ["강점1", "강점2"]})
    """
    sections: dict[str, list[str]] = {}

    # swot_analysis 섹션
    swot = report_dict.get("swot_analysis", {})
    for key in ["strength", "weakness", "opportunity", "threat"]:
        items = swot.get(key, [])
        if isinstance(items, list):
            non_default = [s for s in items if s and "정보 부족" not in s and not _is_meaningless_value(s)]
            if non_default:
                sections[f"swot_analysis.{key}"] = non_default

    for key in ["so_strategy", "wt_strategy"]:
        value = swot.get(key, "")
        if value and "정보 부족" not in value and not _is_meaningless_value(value):
            sections[f"swot_analysis.{key}"] = [value]

    # interview_preparation 섹션
    interview = report_dict.get("interview_preparation", {})
    for key in ["recent_issues", "pressure_questions", "expected_answers"]:
        items = interview.get(key, [])
        if isinstance(items, list):
            non_default = [s for s in items if s and "정보 부족" not in s and not _is_meaningless_value(s)]
            if non_default:
                sections[f"interview_preparation.{key}"] = non_default

    return sections
