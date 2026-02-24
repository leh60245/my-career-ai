"""
자동 교정 Refiner (교정 에이전트)

역할:
    - Evaluator가 도출한 환각 지적 리스트를 기반으로 JSON 초안을 자동 교정합니다.
    - 지적받은 문장을 원천 데이터에 기반하여 팩트 위주로 재작성하거나,
      근거할 팩트가 전혀 없다면 해당 문장을 JSON 초안에서 완전히 삭제합니다.

교정 룰:
    - instruction이 'rewrite'인 경우: 원천 데이터에 기반하여 재작성
    - instruction이 'delete'인 경우: 해당 문장을 JSON에서 삭제
    - 2회 반복 후에도 환각이 남아있으면 강제 삭제 처리
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.src.common.config import AI_CONFIG
from backend.src.company.engine.evaluator import EvaluationResult, HallucinationFinding


logger = logging.getLogger(__name__)


# ============================================================
# Pydantic 출력 스키마
# ============================================================


class RefinementResult(BaseModel):
    """Refiner의 교정 결과"""

    refined_json: dict[str, Any] = Field(description="교정이 완료된 JSON 리포트")
    changes_made: list[str] = Field(default_factory=list, description="수행된 교정 작업 목록")
    forced_deletions: list[str] = Field(default_factory=list, description="강제 삭제된 항목 목록")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Refiner 시스템 프롬프트
# ============================================================

REFINER_SYSTEM_PROMPT = (
    "당신은 AI가 생성한 기업 분석 보고서의 팩트 오류를 교정하는 전문 교정 에이전트입니다.\n\n"
    "## 핵심 임무\n"
    "Evaluator(심사관)가 도출한 환각 지적 리스트를 기반으로 JSON 초안을 교정하십시오.\n\n"
    "## 교정 규칙 (엄격 준수)\n"
    "1. instruction이 'rewrite'인 항목:\n"
    "   - 원천 데이터(Source Context)에서 관련 근거를 찾아 해당 문장을 팩트 위주로 재작성하십시오.\n"
    "   - 재작성 시 원천 데이터에 명시된 수치/사실만 사용하고, 추론이나 추측을 삽입하지 마십시오.\n"
    "2. instruction이 'delete'인 항목:\n"
    "   - 해당 문장을 JSON에서 완전히 삭제하십시오.\n"
    "   - 배열(array) 필드에서 삭제 시, 배열이 비게 되면 '정보 부족 - 추가 조사 필요'를 기본값으로 삽입하십시오.\n"
    "   - 문자열(string) 필드에서 삭제 시, '정보 부족 - 추가 조사 필요'로 대체하십시오.\n"
    "3. Evaluator가 지적하지 않은 항목은 절대 수정하지 마십시오.\n\n"
    "## 출력 규칙 (엄격 준수)\n"
    "1. 출력은 반드시 교정이 완료된 전체 JSON 리포트를 순수 JSON 문자열로 반환하십시오.\n"
    "2. 기존 JSON 구조(키, 중첩 구조)를 변경하지 마십시오.\n"
    "3. 마크다운 백틱(```)이나 부연 설명 텍스트를 절대 포함하지 마십시오.\n"
)


# ============================================================
# Refiner 핵심 로직
# ============================================================


def _build_refinement_prompt(
    draft_json: str, evaluation: EvaluationResult, source_context: str, company_name: str
) -> str:
    """
    Refiner에게 전달할 사용자 프롬프트를 구성합니다.

    Args:
        draft_json: 1차 생성된 JSON 초안
        evaluation: Evaluator의 평가 결과
        source_context: 원천 검색 데이터 컨텍스트
        company_name: 분석 대상 기업명

    Returns:
        Refiner 사용자 프롬프트
    """
    findings_json = json.dumps([f.model_dump() for f in evaluation.findings], ensure_ascii=False, indent=2)

    return (
        f"## 교정 대상 기업: {company_name}\n\n"
        f"## 1차 JSON 초안 (교정 대상)\n"
        f"```json\n{draft_json}\n```\n\n"
        f"## Evaluator 환각 지적 리스트\n"
        f"```json\n{findings_json}\n```\n\n"
        f"## 원천 데이터 (Source Context)\n"
        f"{source_context}\n\n"
        f"위 환각 지적 리스트의 각 항목에 대해 교정 규칙에 따라 JSON을 수정하고, "
        f"교정이 완료된 전체 JSON을 반환하십시오."
    )


async def refine_report(
    draft_json: str,
    evaluation: EvaluationResult,
    source_context: str,
    company_name: str,
    model_provider: str = "openai",
) -> RefinementResult:
    """
    Evaluator의 지적을 기반으로 JSON 초안을 교정합니다.

    Args:
        draft_json: 1차 생성된 JSON 리포트 (문자열)
        evaluation: Evaluator의 평가 결과
        source_context: 원천 검색 데이터 컨텍스트
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더 ('openai' 또는 'gemini')

    Returns:
        RefinementResult: 교정 결과
    """
    import asyncio

    import litellm

    user_prompt = _build_refinement_prompt(draft_json, evaluation, source_context, company_name)

    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key")
    else:
        model = "gpt-4o"
        api_key = AI_CONFIG.get("openai_api_key")

    if not api_key:
        raise ValueError(f"{model_provider} API 키가 설정되지 않았습니다.")

    messages = [{"role": "system", "content": REFINER_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: litellm.completion(
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=0.1,
            max_tokens=8000,
            response_format={"type": "json_object"},
        ),
    )

    content = response.choices[0].message.content  # type: ignore[union-attr]
    if content is None:
        raise ValueError("Refiner LLM이 빈 응답을 반환했습니다.")

    return _parse_refinement_result(content, evaluation)


def _parse_refinement_result(raw_text: str, evaluation: EvaluationResult) -> RefinementResult:
    """
    Refiner LLM 응답을 RefinementResult로 파싱합니다.

    Args:
        raw_text: LLM 응답 텍스트
        evaluation: 원본 Evaluator 결과 (변경사항 기록용)

    Returns:
        RefinementResult 객체
    """
    from backend.src.company.engine.json_utils import extract_json_string

    try:
        json_str = extract_json_string(raw_text)
        refined_data = json.loads(json_str)

        changes = []
        for finding in evaluation.findings:
            action = "재작성" if finding.instruction == "rewrite" else "삭제"
            changes.append(f"[{finding.section}] {action}: {finding.statement[:50]}...")

        return RefinementResult(refined_json=refined_data, changes_made=changes, forced_deletions=[])
    except Exception as e:
        logger.error(f"Refiner 응답 파싱 실패: {e}")
        # 파싱 실패 시 원본 JSON 유지
        try:
            original_data = json.loads(extract_json_string(raw_text))
        except Exception:
            original_data = json.loads(raw_text) if raw_text.strip().startswith("{") else {}

        return RefinementResult(
            refined_json=original_data, changes_made=[f"Refiner 파싱 실패로 원본 유지: {e}"], forced_deletions=[]
        )


def force_delete_hallucinations(
    report_dict: dict[str, Any], findings: list[HallucinationFinding]
) -> tuple[dict[str, Any], list[str]]:
    """
    2회 반복 후에도 남아있는 환각을 강제 삭제합니다.

    무한 루프를 원천 차단하기 위해, 추가 교정을 시도하지 않고
    해당 문장 자체를 최종 JSON에서 제거합니다.

    Args:
        report_dict: 현재 JSON 리포트 딕셔너리
        findings: 여전히 남아있는 환각 항목 리스트

    Returns:
        (교정된 딕셔너리, 강제 삭제된 항목 설명 리스트)
    """
    DEFAULT_VALUE = "정보 부족 - 추가 조사 필요"
    forced_deletions: list[str] = []

    for finding in findings:
        section_path = finding.section  # 예: "swot_analysis.strength"
        statement = finding.statement

        parts = section_path.split(".")
        if len(parts) != 2:
            logger.warning(f"강제 삭제 건너뜀 - 잘못된 섹션 경로: {section_path}")
            continue

        top_section, field_name = parts

        if top_section not in report_dict:
            logger.warning(f"강제 삭제 건너뜀 - 섹션 없음: {top_section}")
            continue

        section_data = report_dict[top_section]
        if field_name not in section_data:
            logger.warning(f"강제 삭제 건너뜀 - 필드 없음: {section_path}")
            continue

        field_value = section_data[field_name]

        if isinstance(field_value, list):
            # 배열에서 해당 문장 제거
            original_len = len(field_value)
            section_data[field_name] = [item for item in field_value if item != statement]
            removed_count = original_len - len(section_data[field_name])

            # 배열이 비었으면 기본값 삽입
            if not section_data[field_name]:
                section_data[field_name] = [DEFAULT_VALUE]

            if removed_count > 0:
                forced_deletions.append(f"[강제 삭제] {section_path}: '{statement[:50]}...' 제거 완료")
            else:
                logger.warning(f"강제 삭제 대상 문장을 찾지 못함: {section_path} - '{statement[:50]}...'")

        elif isinstance(field_value, str):
            # 문자열 필드는 기본값으로 대체
            if field_value == statement or statement in field_value:
                section_data[field_name] = DEFAULT_VALUE
                forced_deletions.append(f"[강제 삭제] {section_path}: 기본값으로 대체 완료")

    return report_dict, forced_deletions
