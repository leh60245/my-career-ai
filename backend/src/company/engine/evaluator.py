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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("has_hallucination", mode="before")
    @classmethod
    def coerce_has_hallucination(cls, v):
        """Gemini가 bool 대신 문자열('true'/'false')을 반환하는 경우 정규화."""
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return v

    @field_validator("findings", mode="before")
    @classmethod
    def coerce_findings_to_list(cls, v):
        """LLM이 findings 필드를 비정규 형식으로 반환하는 경우 정규화.

        Gemini 등 일부 프로바이더가 findings를 문자열 배열이나
        필수 키가 누락된 dict 배열로 반환하는 케이스를 방어합니다.
        """
        if isinstance(v, str):
            logger.warning(f"findings 필드가 문자열('{v[:100]}')로 수신됨. 빈 리스트로 정규화합니다.")
            return []
        if v is None:
            return []
        if not isinstance(v, list):
            return []

        normalized: list[dict] = []
        for idx, item in enumerate(v):
            if isinstance(item, BaseModel):
                # 이미 HallucinationFinding 인스턴스인 경우 dict로 변환하여 통과
                normalized.append(item.model_dump())
            elif isinstance(item, str):
                # Gemini가 findings를 문자열 배열로 반환하는 경우
                logger.warning(f"findings[{idx}]가 문자열로 수신됨. HallucinationFinding dict로 변환합니다.")
                normalized.append(
                    {
                        "section": "unknown",
                        "statement": item,
                        "reason": "LLM이 구조화되지 않은 문자열로 반환",
                        "instruction": "rewrite",
                    }
                )
            elif isinstance(item, dict):
                # 필수 키 누락 시 기본값으로 보충
                coerced = dict(item)
                if "statement" not in coerced:
                    # section/instruction 등 다른 키에서 문맥 추출 시도
                    fallback_text = coerced.get("section", "") or coerced.get("description", "") or str(coerced)
                    coerced["statement"] = fallback_text
                    logger.warning(f"findings[{idx}]에 'statement' 키 누락. fallback 값으로 보충합니다.")
                if "reason" not in coerced:
                    coerced["reason"] = coerced.get("description", "LLM 응답에서 reason 키 누락")
                    logger.warning(f"findings[{idx}]에 'reason' 키 누락. 기본값으로 보충합니다.")
                if "section" not in coerced:
                    coerced["section"] = "unknown"
                if "instruction" not in coerced:
                    coerced["instruction"] = "rewrite"
                normalized.append(coerced)
            else:
                logger.warning(f"findings[{idx}]가 예상치 못한 타입({type(item).__name__})입니다. 건너뜁니다.")
                continue
        return normalized

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
        "## 미래 전망치 환각 탐지 규칙 (신규)\n"
        "- 애널리스트 추정치, 컨센서스, 시장 전망치 등을 확정 사실처럼 서술한 문장은 환각으로 판정합니다.\n"
        "- '~할 것으로 예상', '~할 전망', '~에 달할 것으로 추정' 등 미래 표현이 포함된 수치 서술은 환각으로 판정합니다.\n"
        "- 단, 기업의 공식 발표 계획(예: '2025년까지 투자 계획 발표')은 출처가 확인되면 환각이 아닙니다.\n"
        "- 직전 회계연도 확정 실적(DART/KIND 공시 기준)이 아닌 미래 추정 재무 수치는 환각으로 판정합니다.\n"
        "- instruction: 미래 전망치를 인용한 문장은 'rewrite'로 판정하고, "
        "reason에 '미래 전망치/추정치 사용 - 확정 실적으로 교체 필요'라고 명시하십시오.\n\n"
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
        logger.error(f"Evaluator 응답 파싱 실패: {e}, 원본 응답(앞 500자): {raw_text[:500]}")
        # Fail-safe: 파싱 실패 시 예외를 상위로 전파하여 검증 무력화를 방지
        raise ValueError(f"Evaluator 응답 스키마 검증 실패: {e}") from e


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
