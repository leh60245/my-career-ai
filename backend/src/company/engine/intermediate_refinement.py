"""
중간 정제 파이프라인 (Intermediate Refinement Pipeline)

역할:
    - QuestionToQuery: 단일 질문을 다각화된 검색 쿼리 배열로 확장합니다.
    - AnswerQuestion: 검색 결과 원시 텍스트에서 목차별 핵심 답변을 추출/압축합니다.
    - 기존 파이프라인에서 원시 검색 결과를 최종 LLM에 직결하던 로직을 대체합니다.

참고:
    - STORM의 QuestionToQuery / AnswerQuestion Signature 설계를 참조하되,
      DSPy 프레임워크 대신 litellm 직접 호출로 구현합니다.
    - 동시성 제어: asyncio.Semaphore 기반 Rate Limit 방어.
    - Context Starvation 방어: 검색 결과 0건 시 빈 문자열 반환.
"""

import asyncio
import json
import logging
from datetime import date
from typing import Any


logger = logging.getLogger(__name__)

# 동시성 제어 상수
MAX_CONCURRENT_LLM_CALLS = 5
LLM_RETRY_COUNT = 2
LLM_RETRY_DELAY_SEC = 1.0

# QuestionToQuery 시스템 프롬프트
_QUESTION_TO_QUERY_SYSTEM_PROMPT = (
    "당신은 기업 분석을 위한 검색 전문가입니다. "
    "아래 주어진 분석 질문에 대해, Google 검색에 입력할 최적의 검색 쿼리를 생성하십시오.\n\n"
    "## 규칙\n"
    "1. 하나의 질문에 대해 3~5개의 다각화된 검색 쿼리를 생성하십시오.\n"
    "2. 재무 데이터 관련 질문에는 반드시 현재 연도({year})와 '사업보고서', 'DART', '실적' 등의 키워드를 포함하십시오.\n"
    "3. 최신 뉴스/이슈 관련 질문에는 '{year} 최신', '최근', '뉴스' 등의 시간 키워드를 포함하십시오.\n"
    "4. 한국 기업에 대해서는 한국어 키워드를 우선 사용하되, 글로벌 데이터가 필요하면 영문 쿼리도 추가하십시오.\n"
    "5. 각 쿼리에 반드시 기업명({company_name})을 포함하십시오.\n\n"
    "## 출력 형식\n"
    "반드시 아래 JSON 형식으로만 응답하십시오:\n"
    '{{"queries": ["쿼리1", "쿼리2", "쿼리3"]}}\n'
)

# AnswerQuestion 시스템 프롬프트
_ANSWER_QUESTION_SYSTEM_PROMPT = (
    "당신은 수집된 검색 결과에서 핵심 정보를 정확하게 추출하는 정보 분석 전문가입니다.\n\n"
    "## 역할\n"
    "주어진 검색 결과(스니펫)를 읽고, 질문에 대한 핵심 답변을 1차 추출 및 압축하십시오.\n\n"
    "## 규칙\n"
    "1. 검색 결과에 명시적으로 포함된 사실만 추출하십시오. 추측이나 창작은 절대 금지입니다.\n"
    "2. 숫자 데이터(매출액, 영업이익, 점유율 등)는 반드시 단위와 기준 시점을 명시하십시오.\n"
    "3. 출처를 알 수 있는 경우 해당 정보의 출처 URL을 [출처: URL] 형태로 문장 끝에 표기하십시오.\n"
    "4. 검색 결과가 질문과 직접 관련이 없는 경우, 가장 관련 높은 정보만 추출하십시오.\n"
    "5. 추출할 정보가 전혀 없는 경우, 빈 문자열을 반환하십시오.\n"
    "6. 답변은 300자 이내로 간결하게 압축하고, 개조식(Bullet Point)으로 작성하십시오.\n\n"
    "## 출력 형식\n"
    "반드시 아래 JSON 형식으로만 응답하십시오:\n"
    '{{"answer": "추출된 핵심 답변 텍스트"}}\n'
)


async def expand_queries(
    question: str, company_name: str, model_provider: str = "openai", max_queries: int = 5
) -> list[str]:
    """
    단일 질문을 다각화된 검색 쿼리 배열로 확장합니다.

    Args:
        question: 원본 검색 질문
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더 ('openai' 또는 'gemini')
        max_queries: 생성할 최대 쿼리 수

    Returns:
        확장된 검색 쿼리 리스트 (실패 시 원본 질문만 포함)
    """
    import litellm

    from backend.src.common.config import AI_CONFIG

    current_year = str(date.today().year)

    system_prompt = _QUESTION_TO_QUERY_SYSTEM_PROMPT.replace("{year}", current_year).replace(
        "{company_name}", company_name
    )

    user_prompt = (
        f"분석 대상 기업: {company_name}\n"
        f"기준 연도: {current_year}\n"
        f"분석 질문: {question}\n\n"
        f"위 질문에 대해 {max_queries}개의 다각화된 검색 쿼리를 JSON으로 생성하십시오."
    )

    # 경량 모델 사용 (비용 최적화)
    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key")
    else:
        model = "gpt-4o-mini"
        api_key = AI_CONFIG.get("openai_api_key")

    if not api_key:
        logger.warning(f"API key 미설정. 원본 쿼리 반환: {question}")
        return [question]

    for attempt in range(1, LLM_RETRY_COUNT + 1):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: litellm.completion(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    api_key=api_key,
                    temperature=0.5,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                ),
            )

            content = response.choices[0].message.content  # type: ignore[union-attr]
            if not content:
                logger.warning(f"QuestionToQuery 빈 응답 (시도 {attempt})")
                continue

            parsed = json.loads(content)
            queries = parsed.get("queries", [])

            if not queries:
                logger.warning(f"QuestionToQuery 빈 쿼리 배열 (시도 {attempt})")
                continue

            # 기업명이 없는 쿼리에 기업명 추가
            result = []
            for q in queries[:max_queries]:
                q = str(q).strip()
                if q and company_name not in q:
                    q = f"{company_name} {q}"
                if q:
                    result.append(q[:200])

            if result:
                logger.info(f"QuestionToQuery 성공: '{question}' -> {len(result)}개 쿼리")
                return result

        except json.JSONDecodeError as e:
            logger.warning(f"QuestionToQuery JSON 파싱 실패 (시도 {attempt}): {e}")
        except Exception as e:
            logger.warning(f"QuestionToQuery LLM 호출 실패 (시도 {attempt}): {e}")

        if attempt < LLM_RETRY_COUNT:
            await asyncio.sleep(LLM_RETRY_DELAY_SEC)

    # Fallback: 원본 질문 반환
    logger.warning(f"QuestionToQuery 全시도 실패. 원본 쿼리 반환: {question}")
    return [question]


async def extract_answer(
    question: str,
    snippets: list[str],
    company_name: str,
    model_provider: str = "openai",
    semaphore: asyncio.Semaphore | None = None,
) -> str:
    """
    검색 결과 스니펫에서 질문에 대한 핵심 답변을 추출/압축합니다.

    Args:
        question: 분석 질문
        snippets: 검색 결과 스니펫 리스트
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더
        semaphore: 동시성 제어용 세마포어 (Rate Limit 방어)

    Returns:
        추출된 핵심 답변 문자열 (실패 또는 정보 없음 시 빈 문자열)
    """
    import litellm

    from backend.src.common.config import AI_CONFIG

    # Context Starvation 방어: 스니펫 없으면 빈 문자열 반환
    if not snippets:
        return ""

    # 스니펫 텍스트를 3,000자 이내로 제한 (경량 LLM 토큰 방어)
    snippets_text = "\n".join(f"- {s.strip()}" for s in snippets if s and s.strip())
    if len(snippets_text) > 3000:
        snippets_text = snippets_text[:3000] + "\n[... 이하 생략 ...]"

    user_prompt = (
        f"분석 대상 기업: {company_name}\n"
        f"질문: {question}\n\n"
        f"검색 결과:\n{snippets_text}\n\n"
        f"위 검색 결과에서 질문에 대한 핵심 답변을 JSON으로 추출하십시오."
    )

    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key")
    else:
        model = "gpt-4o-mini"
        api_key = AI_CONFIG.get("openai_api_key")

    if not api_key:
        logger.warning("API key 미설정. 원시 스니펫 반환")
        return snippets_text[:500]

    async def _call() -> str:
        for attempt in range(1, LLM_RETRY_COUNT + 1):
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: litellm.completion(
                        model=model,
                        messages=[
                            {"role": "system", "content": _ANSWER_QUESTION_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        api_key=api_key,
                        temperature=0.1,
                        max_tokens=500,
                        response_format={"type": "json_object"},
                    ),
                )

                content = response.choices[0].message.content  # type: ignore[union-attr]
                if not content:
                    logger.warning(f"AnswerQuestion 빈 응답 (시도 {attempt})")
                    continue

                parsed = json.loads(content)
                answer = parsed.get("answer", "")
                if answer:
                    return str(answer).strip()

            except json.JSONDecodeError as e:
                logger.warning(f"AnswerQuestion JSON 파싱 실패 (시도 {attempt}): {e}")
            except Exception as e:
                logger.warning(f"AnswerQuestion LLM 호출 실패 (시도 {attempt}): {e}")

            if attempt < LLM_RETRY_COUNT:
                await asyncio.sleep(LLM_RETRY_DELAY_SEC)

        # Fallback: 빈 문자열 반환 (파이프라인 크래시 방지)
        logger.warning(f"AnswerQuestion 全시도 실패. 빈 답변 반환. 질문: {question}")
        return ""

    if semaphore:
        async with semaphore:
            return await _call()
    else:
        return await _call()


async def refine_search_results(
    query_items: list[dict[str, str]],
    search_results_by_query: dict[str, list[dict]],
    company_name: str,
    model_provider: str = "openai",
) -> dict[str, str]:
    """
    Map-Reduce 패턴으로 검색 결과를 질문별 핵심 답변으로 정제합니다.

    각 질문에 대한 검색 결과 스니펫을 병렬로 AnswerQuestion에 전달하여
    핵심 답변을 1차 추출/압축합니다.

    Args:
        query_items: [{"persona": str, "query": str, "tag": str}, ...]
        search_results_by_query: {query -> [{"snippets": [...], ...}, ...]}
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더

    Returns:
        {query -> refined_answer_text} 매핑 딕셔너리
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    tasks: list[tuple[str, Any]] = []

    for item in query_items:
        query = item["query"]
        results = search_results_by_query.get(query, [])

        # 모든 검색 결과에서 스니펫 추출
        all_snippets: list[str] = []
        for r in results:
            snippets = r.get("snippets", [])
            for s in snippets:
                if s and s.strip():
                    all_snippets.append(s.strip())

        tasks.append((query, extract_answer(query, all_snippets, company_name, model_provider, semaphore)))

    # 병렬 실행
    refined: dict[str, str] = {}
    if tasks:
        results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)
        for i, (query, _) in enumerate(tasks):
            result = results[i]
            if isinstance(result, Exception):
                logger.warning(f"AnswerQuestion 비동기 실행 실패: {query} - {result}")
                refined[query] = ""
            else:
                refined[query] = result  # type: ignore[assignment]

    logger.info(f"중간 정제 완료: {len(tasks)}개 질문 처리, 유효 답변 {sum(1 for v in refined.values() if v)}개")

    return refined
