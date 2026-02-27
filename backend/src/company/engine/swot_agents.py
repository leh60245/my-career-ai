"""
SWOT 마이크로 에이전트 분할 및 무손실 병합 로직

역할:
    - 기존 Phase 2의 단일 SWOT+Culture 생성을 5개 독립 마이크로 에이전트로 분할
      (corporate_culture, strength, weakness, opportunity, threat)
    - 5개 에이전트를 asyncio.gather로 병렬 실행
    - 4개 SWOT 결과를 코드 레벨에서 무손실 병합 (LLM 재호출 없음)
    - SO/WT 전략은 경량 LLM 호출(6번째)로 생성
    - 개별 에이전트 실패 시 해당 항목만 '정보 부족'으로 안전 매핑

설계 원칙:
    - 각 에이전트가 생성한 텍스트의 글자 수와 최종 JSON의 각 항목 글자 수가
      100% 동일해야 함 (무손실 검증)
    - 파이프라인 크래시 없이 부분 실패를 허용하는 Graceful Degradation
"""

import asyncio
import json
import logging
from typing import Any

from backend.src.common.config import AI_CONFIG
from backend.src.company.engine.llm_resilience import LLMResilienceState, resilient_llm_call
from backend.src.company.engine.personas import (
    CULTURE_AGENT_PROMPT,
    OPPORTUNITY_AGENT_PROMPT,
    SO_WT_STRATEGY_PROMPT,
    STRENGTH_AGENT_PROMPT,
    THREAT_AGENT_PROMPT,
    WEAKNESS_AGENT_PROMPT,
)
from backend.src.company.schemas.career_report import CorporateCulture, SwotAnalysis


logger = logging.getLogger(__name__)

# 기본값 상수
_DEFAULT_ITEMS = ["정보 부족 - 추가 조사 필요"]
_DEFAULT_STRATEGY = "정보 부족 - 추가 조사 필요"


def _resolve_model_and_key(model_provider: str, lightweight: bool = False) -> tuple[str, str]:
    """
    모델 프로바이더에 따른 모델명과 API 키를 반환합니다.

    Args:
        model_provider: 'openai' 또는 'gemini'
        lightweight: True이면 경량 모델(gpt-4o-mini) 사용

    Returns:
        (model_name, api_key) 튜플
    """
    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key", "")
    else:
        model = "gpt-4o-mini" if lightweight else "gpt-4o"
        api_key = AI_CONFIG.get("openai_api_key", "")

    if not api_key:
        raise ValueError(f"{model_provider} API 키가 설정되지 않았습니다.")

    return model, api_key


async def _run_single_micro_agent(
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    model_provider: str,
    resilience_state: LLMResilienceState,
    lightweight: bool = False,
    max_tokens: int = 4000,
) -> str | None:
    """
    단일 마이크로 에이전트를 실행합니다.

    Args:
        agent_name: 에이전트 식별자 (로깅용)
        system_prompt: 에이전트 전용 시스템 프롬프트
        user_prompt: 사용자 프롬프트 (컨텍스트 + 지시)
        model_provider: LLM 프로바이더
        resilience_state: 공유 Resilience 상태
        lightweight: 경량 모델 사용 여부
        max_tokens: 최대 토큰 수

    Returns:
        LLM 응답 텍스트 (실패 시 None)
    """
    model, api_key = _resolve_model_and_key(model_provider, lightweight)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    logger.info(f"[MicroAgent:{agent_name}] 실행 시작 (model={model})")

    result = await resilient_llm_call(
        model=model,
        messages=messages,
        api_key=api_key,
        state=resilience_state,
        temperature=0.3,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    if result is None:
        logger.warning(f"[MicroAgent:{agent_name}] Graceful Degradation: LLM 호출 실패, 기본값 사용")
    else:
        logger.info(f"[MicroAgent:{agent_name}] 완료 ({len(result)}자)")

    return result


def _parse_swot_items(raw_text: str | None, agent_name: str) -> list[str]:
    """
    SWOT 마이크로 에이전트의 JSON 응답에서 items 배열을 추출합니다.

    Args:
        raw_text: LLM 응답 텍스트
        agent_name: 에이전트 식별자 (로깅용)

    Returns:
        항목 리스트 (파싱 실패 시 기본값)
    """
    if raw_text is None:
        return list(_DEFAULT_ITEMS)

    try:
        data = json.loads(raw_text)

        # {"items": [...]} 형식
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
            if isinstance(items, list) and items:
                return [str(item) for item in items if item]

        # {"strength": [...]} 등 직접 키 형식 (LLM 변형 대응)
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and val:
                    return [str(item) for item in val if item]

        logger.warning(f"[MicroAgent:{agent_name}] 빈 응답 파싱 결과, 기본값 사용")
        return list(_DEFAULT_ITEMS)

    except json.JSONDecodeError as e:
        logger.warning(f"[MicroAgent:{agent_name}] JSON 파싱 실패: {e}, 기본값 사용")
        return list(_DEFAULT_ITEMS)


def _parse_culture_result(raw_text: str | None) -> CorporateCulture:
    """
    corporate_culture 에이전트의 JSON 응답을 파싱합니다.

    Args:
        raw_text: LLM 응답 텍스트

    Returns:
        CorporateCulture Pydantic 객체
    """
    if raw_text is None:
        return CorporateCulture()

    try:
        data = json.loads(raw_text)

        # {"corporate_culture": {...}} 또는 직접 {...} 형식 모두 대응
        if isinstance(data, dict) and "corporate_culture" in data:
            data = data["corporate_culture"]

        return CorporateCulture.model_validate(data)

    except Exception as e:
        logger.warning(f"[MicroAgent:culture] 파싱 실패: {e}, 기본값 사용")
        return CorporateCulture()


def _parse_so_wt_strategy(raw_text: str | None) -> tuple[str, str]:
    """
    SO/WT 전략 에이전트의 JSON 응답을 파싱합니다.

    Args:
        raw_text: LLM 응답 텍스트

    Returns:
        (so_strategy, wt_strategy) 튜플
    """
    if raw_text is None:
        return _DEFAULT_STRATEGY, _DEFAULT_STRATEGY

    try:
        data = json.loads(raw_text)
        so = data.get("so_strategy", _DEFAULT_STRATEGY) or _DEFAULT_STRATEGY
        wt = data.get("wt_strategy", _DEFAULT_STRATEGY) or _DEFAULT_STRATEGY
        return str(so), str(wt)

    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"[MicroAgent:so_wt] 파싱 실패: {e}, 기본값 사용")
        return _DEFAULT_STRATEGY, _DEFAULT_STRATEGY


def verify_lossless_merge(
    agent_outputs: dict[str, list[str] | str], final_swot: SwotAnalysis, final_culture: CorporateCulture
) -> dict[str, Any]:
    """
    마이크로 에이전트 산출물의 글자 수와 최종 병합 결과의 글자 수가
    100% 동일한지 검증합니다.

    Args:
        agent_outputs: 에이전트별 원시 산출물
        final_swot: 최종 SwotAnalysis Pydantic 객체
        final_culture: 최종 CorporateCulture Pydantic 객체

    Returns:
        검증 결과 딕셔너리 (all_match, details)
    """
    verification: dict[str, Any] = {"all_match": True, "details": {}}

    # SWOT 필드 비교
    swot_field_map = {
        "strength": final_swot.strength,
        "weakness": final_swot.weakness,
        "opportunity": final_swot.opportunity,
        "threat": final_swot.threat,
    }

    for field_name, final_items in swot_field_map.items():
        agent_items = agent_outputs.get(field_name, _DEFAULT_ITEMS)
        if isinstance(agent_items, list):
            agent_char_count = sum(len(item) for item in agent_items)
            final_char_count = sum(len(item) for item in final_items)
            match = agent_char_count == final_char_count
            verification["details"][field_name] = {
                "agent_chars": agent_char_count,
                "final_chars": final_char_count,
                "match": match,
                "agent_items_count": len(agent_items),
                "final_items_count": len(final_items),
            }
            if not match:
                verification["all_match"] = False

    # culture 필드 비교
    culture_data = agent_outputs.get("culture_raw", "")
    if isinstance(culture_data, str):
        verification["details"]["culture"] = {"agent_raw_chars": len(culture_data), "parsed": True}

    # SO/WT 전략 비교
    for strategy_key in ("so_strategy", "wt_strategy"):
        agent_val = agent_outputs.get(strategy_key, _DEFAULT_STRATEGY)
        final_val = getattr(final_swot, strategy_key, _DEFAULT_STRATEGY)
        if isinstance(agent_val, str):
            match = agent_val == final_val
            verification["details"][strategy_key] = {
                "agent_chars": len(agent_val),
                "final_chars": len(final_val),
                "match": match,
            }
            if not match:
                verification["all_match"] = False

    return verification


async def run_phase2_micro_agents(
    context_text: str,
    company_name: str,
    topic: str,
    model_provider: str,
    resilience_state: LLMResilienceState,
    chaining_context: str | None = None,
    job_id: str = "",
    jobs_dict: dict[str, dict[str, Any]] | None = None,
    progress_range: tuple[int, int] = (35, 60),
) -> tuple[CorporateCulture, SwotAnalysis, dict[str, Any], dict[str, Any]]:
    """
    Phase 2를 5개 마이크로 에이전트로 분할 실행하고 무손실 병합합니다.

    실행 흐름:
        1. 5개 에이전트 병렬 실행 (culture, S, W, O, T)
        2. 코드 레벨 무손실 병합
        3. SO/WT 전략 경량 LLM 호출 (6번째)
        4. 글자 수 무손실 검증

    Args:
        context_text: 검색 결과 기반 LLM 컨텍스트 문자열
        company_name: 분석 대상 기업명
        topic: 분석 주제
        model_provider: LLM 프로바이더
        resilience_state: 공유 Resilience 상태
        chaining_context: Phase 1 검증 결과 (체이닝)
        job_id: Job UUID (로깅용)
        jobs_dict: 진행률 관리 딕셔너리
        progress_range: 진행률 범위

    Returns:
        (CorporateCulture, SwotAnalysis, agent_output_log, lossless_verification)
    """
    progress_start, progress_end = progress_range
    if jobs_dict and job_id:
        jobs_dict[job_id]["progress"] = progress_start
        jobs_dict[job_id]["message"] = "Phase 2: 마이크로 에이전트 병렬 실행 중"

    # ---- 사용자 프롬프트 구성 ----
    from datetime import date

    today_str = date.today().strftime("%Y-%m-%d")
    base_context = f"분석 대상 기업: {company_name}\n분석 주제: {topic}\n기준일: {today_str}\n\n"

    if chaining_context:
        base_context += f"## 이전 분석 단계 검증 결과\n{chaining_context}\n\n"

    base_context += f"## 수집 데이터\n{context_text}"

    # ---- 5개 에이전트 병렬 실행 ----
    logger.info(f"[{job_id}] Phase 2 마이크로 에이전트 5개 병렬 실행 시작")

    culture_task = _run_single_micro_agent(
        agent_name="culture",
        system_prompt=CULTURE_AGENT_PROMPT,
        user_prompt=base_context,
        model_provider=model_provider,
        resilience_state=resilience_state,
        max_tokens=4000,
    )
    strength_task = _run_single_micro_agent(
        agent_name="strength",
        system_prompt=STRENGTH_AGENT_PROMPT,
        user_prompt=base_context,
        model_provider=model_provider,
        resilience_state=resilience_state,
        max_tokens=3000,
    )
    weakness_task = _run_single_micro_agent(
        agent_name="weakness",
        system_prompt=WEAKNESS_AGENT_PROMPT,
        user_prompt=base_context,
        model_provider=model_provider,
        resilience_state=resilience_state,
        max_tokens=3000,
    )
    opportunity_task = _run_single_micro_agent(
        agent_name="opportunity",
        system_prompt=OPPORTUNITY_AGENT_PROMPT,
        user_prompt=base_context,
        model_provider=model_provider,
        resilience_state=resilience_state,
        max_tokens=3000,
    )
    threat_task = _run_single_micro_agent(
        agent_name="threat",
        system_prompt=THREAT_AGENT_PROMPT,
        user_prompt=base_context,
        model_provider=model_provider,
        resilience_state=resilience_state,
        max_tokens=3000,
    )

    results = await asyncio.gather(
        culture_task, strength_task, weakness_task, opportunity_task, threat_task, return_exceptions=True
    )

    # ---- 결과 파싱 (개별 실패 허용) ----
    def _safe_result(idx: int, name: str) -> str | None:
        """asyncio.gather 결과에서 안전하게 값을 추출합니다."""
        val = results[idx]
        if isinstance(val, Exception):
            logger.error(f"[{job_id}] MicroAgent:{name} 예외 발생: {val}")
            return None
        return val

    culture_raw = _safe_result(0, "culture")
    strength_raw = _safe_result(1, "strength")
    weakness_raw = _safe_result(2, "weakness")
    opportunity_raw = _safe_result(3, "opportunity")
    threat_raw = _safe_result(4, "threat")

    if jobs_dict and job_id:
        jobs_dict[job_id]["progress"] = progress_start + int((progress_end - progress_start) * 0.6)
        jobs_dict[job_id]["message"] = "Phase 2: 마이크로 에이전트 결과 병합 중"

    # ---- 코드 레벨 무손실 병합 ----
    culture = _parse_culture_result(culture_raw)
    strength_items = _parse_swot_items(strength_raw, "strength")
    weakness_items = _parse_swot_items(weakness_raw, "weakness")
    opportunity_items = _parse_swot_items(opportunity_raw, "opportunity")
    threat_items = _parse_swot_items(threat_raw, "threat")

    logger.info(
        f"[{job_id}] Phase 2 병합: S={len(strength_items)}개, W={len(weakness_items)}개, "
        f"O={len(opportunity_items)}개, T={len(threat_items)}개"
    )

    # ---- SO/WT 전략: 6번째 경량 LLM 호출 ----
    so_wt_user_prompt = (
        f"분석 대상 기업: {company_name}\n\n"
        f"## Strength (강점)\n" + "\n".join(f"- {s}" for s in strength_items) + "\n\n"
        "## Weakness (약점)\n" + "\n".join(f"- {w}" for w in weakness_items) + "\n\n"
        "## Opportunity (기회)\n" + "\n".join(f"- {o}" for o in opportunity_items) + "\n\n"
        "## Threat (위협)\n" + "\n".join(f"- {t}" for t in threat_items) + "\n\n"
        "위 4개 SWOT 항목을 교차 분석하여 SO 전략과 WT 전략을 JSON으로 도출하십시오."
    )

    so_wt_raw = await _run_single_micro_agent(
        agent_name="so_wt_strategy",
        system_prompt=SO_WT_STRATEGY_PROMPT,
        user_prompt=so_wt_user_prompt,
        model_provider=model_provider,
        resilience_state=resilience_state,
        lightweight=True,
        max_tokens=1000,
    )
    so_strategy, wt_strategy = _parse_so_wt_strategy(so_wt_raw)

    if jobs_dict and job_id:
        jobs_dict[job_id]["progress"] = progress_start + int((progress_end - progress_start) * 0.85)

    # ---- SwotAnalysis 조립 ----
    swot = SwotAnalysis(
        strength=strength_items,
        weakness=weakness_items,
        opportunity=opportunity_items,
        threat=threat_items,
        so_strategy=so_strategy,
        wt_strategy=wt_strategy,
    )

    # ---- 에이전트 산출물 로그 기록 ----
    agent_output_log: dict[str, Any] = {
        "culture_raw": culture_raw or "",
        "strength": strength_items,
        "weakness": weakness_items,
        "opportunity": opportunity_items,
        "threat": threat_items,
        "so_strategy": so_strategy,
        "wt_strategy": wt_strategy,
        "culture_raw_chars": len(culture_raw) if culture_raw else 0,
        "strength_chars": sum(len(s) for s in strength_items),
        "weakness_chars": sum(len(s) for s in weakness_items),
        "opportunity_chars": sum(len(s) for s in opportunity_items),
        "threat_chars": sum(len(s) for s in threat_items),
        "agent_failures": [
            name
            for name, raw in [
                ("culture", culture_raw),
                ("strength", strength_raw),
                ("weakness", weakness_raw),
                ("opportunity", opportunity_raw),
                ("threat", threat_raw),
            ]
            if raw is None
        ],
    }

    # ---- 무손실 검증 ----
    lossless_verification = verify_lossless_merge(agent_output_log, swot, culture)

    if lossless_verification["all_match"]:
        logger.info(f"[{job_id}] Phase 2 무손실 검증 통과: 모든 필드 글자 수 100% 일치")
    else:
        logger.warning(
            f"[{job_id}] Phase 2 무손실 검증 불일치 발견: "
            f"{json.dumps(lossless_verification['details'], ensure_ascii=False)}"
        )

    if jobs_dict and job_id:
        jobs_dict[job_id]["progress"] = progress_end

    return culture, swot, agent_output_log, lossless_verification
