"""
Career AI Pipeline (하드코딩 페르소나 기반 기업 분석 파이프라인)

역할:
    - 기존 STORMWikiRunner의 동적 파이프라인(gen_perspectives, direct_gen_outline, refine_outline)을
      완전히 우회(Bypass)합니다.
    - 3가지 고정 페르소나의 하드코딩 쿼리 큐를 사용하여 검색을 수행합니다.
    - 검색 결과를 종합하여 LLM에게 순수 JSON 형태의 구조화된 보고서를 생성하도록 요청합니다.
    - Pydantic 스키마 검증 + JSON 파싱 방어 로직 + 재시도(Retry) 로직을 적용합니다.

Happy Path:
    1. 고정 페르소나 쿼리 큐 로드 → 2. 쿼리 후처리(키워드 강제 조합) →
    3. HybridRM 검색 → 4. LLM JSON 생성 → 5. 파싱/검증 → 6. DB 적재 (COMPLETED)
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import date
from typing import Any

from backend.src.common.config import AI_CONFIG
from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.enums import ReportJobStatus
from backend.src.company.engine.evaluator import evaluate_report
from backend.src.company.engine.json_utils import build_retry_prompt, safe_parse_career_report
from backend.src.company.engine.personas import ALL_PERSONAS, FINAL_SYNTHESIS_PROMPT, build_query_queue
from backend.src.company.engine.refiner import force_delete_hallucinations, refine_report
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.report_job_repository import ReportJobRepository
from backend.src.company.services.report_job_service import ReportJobService

from .io import create_run_directory, write_run_metadata


logger = logging.getLogger(__name__)

# 재시도 횟수 상수
MAX_LLM_RETRIES = 2
# NLI 검증 루프 최대 반복 횟수
MAX_VERIFICATION_LOOPS = 2


async def run_career_pipeline(
    job_id: str, company_name: str, topic: str, jobs_dict: dict[str, dict[str, Any]], model_provider: str = "openai"
) -> None:
    """
    고정 페르소나 기반 기업 분석 파이프라인을 실행합니다.

    Args:
        job_id: Job UUID
        company_name: 분석 대상 기업명
        topic: 분석 주제 (예: "기업 분석")
        jobs_dict: 메모리 기반 상태 관리 딕셔너리
        model_provider: LLM 프로바이더 ('openai' 또는 'gemini')
    """
    logger.info(f"[{job_id}] Career Pipeline 시작: {company_name}")

    jobs_dict[job_id]["status"] = ReportJobStatus.PROCESSING.value
    jobs_dict[job_id]["progress"] = 5

    db_engine = AsyncDatabaseEngine()
    rm = None

    # ================================================================
    # Phase 1: 초기화 및 DB 상태 업데이트
    # ================================================================
    try:
        async with db_engine.get_session() as session:
            job_repo = ReportJobRepository(session)
            job_service = ReportJobService(job_repo)
            await job_service.start_job(job_id)

            company_repo = CompanyRepository(session)
            company = await company_repo.get_by_company_name(company_name)
            if not company:
                raise ValueError(f"Company '{company_name}' not found")
            company_id = company.id
    except Exception as e:
        logger.error(f"[{job_id}] 초기화 실패: {e}")
        jobs_dict[job_id]["status"] = ReportJobStatus.FAILED.value
        jobs_dict[job_id]["message"] = str(e)
        return

    try:
        jobs_dict[job_id]["progress"] = 10

        # ================================================================
        # Phase 2: 고정 쿼리 큐 생성 및 후처리
        # ================================================================
        query_items = build_query_queue(company_name)
        logger.info(f"[{job_id}] 총 {len(query_items)}개 쿼리 큐 생성 완료")

        # 쿼리 후처리: 타겟 키워드 강제 조합
        processed_queries = _post_process_queries(query_items, company_name)
        for pq in processed_queries:
            logger.info(f"[{job_id}] [QueryPostProcess] [{pq['tag']}] {pq['persona']}: {pq['query']}")

        jobs_dict[job_id]["progress"] = 20

        # ================================================================
        # Phase 3: HybridRM 검색 실행
        # ================================================================
        # Lazy import: knowledge_storm 등 무거운 의존성을 실행 시점에만 로드
        from .builder import build_hybrid_rm

        rm = build_hybrid_rm(company_name=company_name, top_k=10)

        search_results_by_persona: dict[str, list[dict]] = {}
        all_search_results: list[dict] = []

        loop = asyncio.get_running_loop()

        for i, pq in enumerate(processed_queries):
            persona_name = pq["persona"]
            query = pq["query"]

            try:
                results = await loop.run_in_executor(None, lambda q=query: rm.forward(q, exclude_urls=[]))

                if persona_name not in search_results_by_persona:
                    search_results_by_persona[persona_name] = []

                # 검색 결과 누락 방어: 빈 결과는 건너뛰고 다음 쿼리로 진행
                if results:
                    search_results_by_persona[persona_name].extend(results)
                    all_search_results.extend(results)
                    logger.info(f"[{job_id}] 쿼리 [{i + 1}/{len(processed_queries)}] '{query}': {len(results)}건")
                else:
                    logger.warning(f"[{job_id}] 쿼리 [{i + 1}/{len(processed_queries)}] '{query}': 결과 없음 (skip)")

            except Exception as e:
                # 개별 쿼리 실패는 파이프라인을 중단하지 않음
                logger.warning(f"[{job_id}] 쿼리 검색 실패 (non-blocking): {query} - {e}")
                continue

            # 진행률 업데이트 (20% ~ 60%)
            progress = 20 + int(40 * (i + 1) / len(processed_queries))
            jobs_dict[job_id]["progress"] = progress

        logger.info(f"[{job_id}] 총 {len(all_search_results)}건 검색 완료")
        jobs_dict[job_id]["progress"] = 60

        # ================================================================
        # Phase 4: LLM에게 JSON 생성 요청 (재시도 로직 포함)
        # ================================================================
        context_text = _build_llm_context(search_results_by_persona, company_name)
        base_prompt = _build_final_prompt(company_name, topic, context_text)

        report_json = None
        last_error = None
        prompt = base_prompt

        for attempt in range(1, MAX_LLM_RETRIES + 2):  # 최초 1회 + 재시도 2회 = 최대 3회
            logger.info(f"[{job_id}] LLM 호출 시도 {attempt}/{MAX_LLM_RETRIES + 1}")

            raw_response = await _call_llm(prompt, model_provider)

            report, error = safe_parse_career_report(raw_response)

            if report is not None:
                report_json = report
                logger.info(f"[{job_id}] JSON 파싱 성공 (시도 {attempt})")
                break

            last_error = error
            logger.warning(f"[{job_id}] JSON 파싱 실패 (시도 {attempt}): {error}")

            if attempt <= MAX_LLM_RETRIES:
                prompt = build_retry_prompt(base_prompt, error or "Unknown error")
            else:
                logger.error(f"[{job_id}] 최대 재시도 횟수 초과. 파이프라인 종료.")

        jobs_dict[job_id]["progress"] = 75

        # ================================================================
        # Phase 4.5: NLI 팩트체크 검증 루프 (Evaluator + Refiner)
        # ================================================================
        if report_json is not None:
            report_json, verification_log = await _run_verification_loop(
                report_json=report_json,
                source_context=context_text,
                company_name=company_name,
                model_provider=model_provider,
                job_id=job_id,
                jobs_dict=jobs_dict,
            )
            logger.info(f"[{job_id}] NLI 검증 루프 완료: {verification_log.get('total_loops', 0)}회 반복")
        else:
            verification_log = {}

        jobs_dict[job_id]["progress"] = 85

        # ================================================================
        # Phase 5: 결과 저장 및 상태 업데이트
        # ================================================================
        if report_json is None:
            # 최종 실패: REJECTED 상태로 변경하고 사유 저장
            async with db_engine.get_session() as session:
                job_repo = ReportJobRepository(session)
                job_service = ReportJobService(job_repo)
                await job_service.reject_job(
                    job_id=job_id, rejection_reason=f"LLM JSON 생성 실패 ({MAX_LLM_RETRIES + 1}회 시도): {last_error}"
                )

            jobs_dict[job_id]["status"] = ReportJobStatus.REJECTED.value
            jobs_dict[job_id]["message"] = f"JSON 생성 실패: {last_error}"
            jobs_dict[job_id]["progress"] = 0
            return

        # DB에 저장
        report_content_json = report_json.model_dump_json(ensure_ascii=False, indent=2)

        # output_dir 생성 (메타데이터 및 로그 저장용)
        base_output_dir = os.path.join("results", "enterprise")
        output_dir = create_run_directory(base_output_dir, company_id, company_name, job_id)

        # 메타데이터 기록
        write_run_metadata(
            output_dir,
            {
                "job_id": job_id,
                "topic": topic,
                "pipeline": "career_pipeline_v1.2",
                "personas": [p.name for p in ALL_PERSONAS],
                "total_queries": len(processed_queries),
                "total_search_results": len(all_search_results),
                "model_provider": model_provider,
                "verification_loops": verification_log.get("total_loops", 0),
            },
        )

        # JSON 결과 파일 저장
        json_output_path = os.path.join(output_dir, "career_analysis_report.json")
        with open(json_output_path, "w", encoding="utf-8") as f:
            f.write(report_content_json)

        # NLI 검증 로그 저장
        if verification_log:
            verification_log_path = os.path.join(output_dir, "verification_log.json")
            with open(verification_log_path, "w", encoding="utf-8") as f:
                json.dump(verification_log, f, ensure_ascii=False, indent=2)

        # 검색 로그 저장
        search_log_path = os.path.join(output_dir, "search_log.json")
        with open(search_log_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "queries": processed_queries,
                    "results_count_by_persona": {k: len(v) for k, v in search_results_by_persona.items()},
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        async with db_engine.get_session() as session:
            job_repo = ReportJobRepository(session)
            job_service = ReportJobService(job_repo)

            # Adapter를 통해 DB 저장
            from backend.src.company.engine.adapter import save_storm_result_from_memory

            report_id = await save_storm_result_from_memory(
                session=session,
                company_name=company_name,
                topic=topic,
                report_content=report_content_json,
                toc_text=_generate_toc_from_report(report_json),
                references_data=_extract_references(all_search_results),
                conversation_log={
                    "pipeline": "career_pipeline_v1.2",
                    "search_queries": processed_queries,
                    "verification_log": verification_log,
                },
                model_name=model_provider,
                meta_info={"job_id": job_id, "file_path": output_dir, "pipeline_version": "v1.2"},
            )

            if report_id is None:
                raise RuntimeError(f"Report DB 저장 실패: job_id={job_id}")

            await job_service.complete_job(job_id)

        jobs_dict[job_id]["status"] = ReportJobStatus.COMPLETED.value
        jobs_dict[job_id]["report_id"] = report_id
        jobs_dict[job_id]["progress"] = 100
        jobs_dict[job_id]["message"] = "완료"

        logger.info(f"[{job_id}] Career Pipeline 완료. Report ID: {report_id}")

    except Exception as e:
        logger.error(f"[{job_id}] Career Pipeline 실행 오류: {e}")
        traceback.print_exc()

        try:
            async with db_engine.get_session() as session:
                job_repo = ReportJobRepository(session)
                job_service = ReportJobService(job_repo)
                await job_service.fail_job(job_id, str(e))
        except Exception as db_e:
            logger.critical(f"[{job_id}] DB 오류 기록 실패: {db_e}")

        jobs_dict[job_id]["status"] = ReportJobStatus.FAILED.value
        jobs_dict[job_id]["message"] = str(e)
        jobs_dict[job_id]["progress"] = 0

    finally:
        if rm and hasattr(rm, "aclose"):
            try:
                await rm.aclose()
            except Exception as close_error:
                logger.warning(f"[{job_id}] HybridRM 종료 실패: {close_error}")


# ============================================================
# 내부 헬퍼 함수
# ============================================================


def _post_process_queries(query_items: list[dict[str, str]], company_name: str) -> list[dict[str, str]]:
    """
    쿼리 후처리: 페르소나별 타겟 키워드를 강제 조합합니다.

    Args:
        query_items: build_query_queue의 결과
        company_name: 기업명

    Returns:
        키워드가 보강된 쿼리 리스트
    """
    # 페르소나별 강제 키워드 맵
    keyword_map = {
        "산업 애널리스트": ["재무", "매출", "시장점유율", "DART"],
        "수석 취업 지원관": ["인재상", "핵심가치", "조직문화", "채용"],
        "실무 면접관": ["면접 기출", "리스크", "논란", "압박 면접"],
    }

    processed = []
    for item in query_items:
        query = item["query"]
        persona = item["persona"]
        tag = item["tag"]

        # 기업명이 쿼리에 없으면 추가
        if company_name not in query:
            query = f"{company_name} {query}"

        # 페르소나별 키워드 중 쿼리에 없는 것 하나를 추가 (쿼리가 너무 길어지는 것 방지)
        keywords = keyword_map.get(persona, [])
        for kw in keywords:
            if kw not in query:
                query = f"{query} {kw}"
                break  # 키워드 1개만 추가

        # 길이 제한
        query = query[:200].strip()

        processed.append({"persona": persona, "query": query, "tag": tag})

    return processed


def _build_llm_context(search_results_by_persona: dict[str, list[dict]], company_name: str) -> str:
    """
    페르소나별 검색 결과를 LLM 컨텍스트 문자열로 변환합니다.

    Args:
        search_results_by_persona: 페르소나별 검색 결과
        company_name: 기업명

    Returns:
        LLM에게 전달할 컨텍스트 문자열
    """
    sections = []

    for persona in ALL_PERSONAS:
        results = search_results_by_persona.get(persona.name, [])
        section_lines = [
            f"\n## [{persona.name}] 수집 데이터",
            f"역할: {persona.role}",
            f"검색 결과: {len(results)}건",
            "",
        ]

        if not results:
            section_lines.append("(검색 결과 없음)")
        else:
            # 중복 제거 및 상위 결과 선택
            seen_snippets: set[str] = set()
            count = 0
            for r in results:
                snippets = r.get("snippets", [])
                title = r.get("title", "")
                url = r.get("url", "")

                for snippet in snippets:
                    snippet_key = snippet[:100] if snippet else ""
                    if snippet_key in seen_snippets:
                        continue
                    seen_snippets.add(snippet_key)

                    source_info = f"[출처: {title}]" if title else ""
                    if url:
                        source_info += f" ({url})"
                    section_lines.append(f"- {snippet.strip()} {source_info}")
                    count += 1

                    if count >= 15:  # 페르소나당 최대 15개 스니펫
                        break

                if count >= 15:
                    break

        sections.append("\n".join(section_lines))

    header = f"# {company_name} 기업 분석을 위한 수집 데이터\n"
    return header + "\n\n".join(sections)


def _build_final_prompt(company_name: str, topic: str, context_text: str) -> str:
    """
    최종 LLM 프롬프트를 조합합니다.

    Args:
        company_name: 기업명
        topic: 분석 주제
        context_text: 검색 결과 컨텍스트

    Returns:
        LLM에게 전달할 최종 프롬프트
    """
    today_str = date.today().strftime("%Y-%m-%d")

    user_instruction = (
        f"분석 대상 기업: {company_name}\n"
        f"분석 주제: {topic}\n"
        f"기준일: {today_str}\n\n"
        f"아래의 수집 데이터를 종합하여 JSON 분석 보고서를 생성하십시오.\n\n"
        f"{context_text}"
    )

    return f"{FINAL_SYNTHESIS_PROMPT}\n\n{user_instruction}"


async def _call_llm(prompt: str, model_provider: str = "openai") -> str:
    """
    LLM을 호출하여 응답을 반환합니다.

    Args:
        prompt: 전체 프롬프트 (시스템 + 사용자)
        model_provider: 'openai' 또는 'gemini'

    Returns:
        LLM 응답 텍스트
    """
    import litellm

    if model_provider == "gemini":
        model = "gemini/gemini-2.0-flash"
        api_key = AI_CONFIG.get("google_api_key")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in config")
    else:
        model = "gpt-4o"
        api_key = AI_CONFIG.get("openai_api_key")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in config")

    messages = [{"role": "system", "content": FINAL_SYNTHESIS_PROMPT}, {"role": "user", "content": prompt}]

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: litellm.completion(
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=0.3,
            max_tokens=8000,
            response_format={"type": "json_object"},
        ),
    )

    content = response.choices[0].message.content  # type: ignore[union-attr]
    if content is None:
        raise ValueError("LLM이 빈 응답을 반환했습니다.")
    return content


def _generate_toc_from_report(report) -> str:
    """
    CareerAnalysisReport에서 목차(TOC) 텍스트를 생성합니다.
    """
    return (
        "1. 기업 개요 (Company Overview)\n"
        "   - 기업 소개\n"
        "   - 업종\n"
        "   - 직원 수\n"
        "   - 본사 위치\n"
        "   - 재무 정보\n"
        "2. 기업 문화 (Corporate Culture)\n"
        "   - 핵심가치\n"
        "   - 인재상\n"
        "   - 조직문화/복리후생\n"
        "3. SWOT 분석\n"
        "   - 강점 (Strength)\n"
        "   - 약점 (Weakness)\n"
        "   - 기회 (Opportunity)\n"
        "   - 위협 (Threat)\n"
        "   - SO 전략\n"
        "   - WT 전략\n"
        "4. 면접 대비 (Interview Preparation)\n"
        "   - 최근 이슈\n"
        "   - 압박 면접 질문\n"
        "   - 전략적 답변 가이드\n"
    )


def _extract_references(all_search_results: list[dict]) -> dict[str, Any]:
    """
    검색 결과에서 참고 URL 목록을 추출합니다.
    """
    refs: dict[str, Any] = {}
    seen_urls: set[str] = set()

    for i, r in enumerate(all_search_results):
        url = r.get("url", "")
        title = r.get("title", f"Source {i + 1}")

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        refs[f"ref_{len(refs) + 1}"] = {"url": url, "title": title}

    return refs


# ============================================================
# NLI 팩트체크 검증 루프
# ============================================================


async def _run_verification_loop(
    report_json,
    source_context: str,
    company_name: str,
    model_provider: str,
    job_id: str,
    jobs_dict: dict[str, dict[str, Any]],
) -> tuple[Any, dict[str, Any]]:
    """
    NLI 기반 팩트체크 검증 루프를 실행합니다.

    3단계 검증 루프:
        1차 JSON 초안 -> Evaluator의 NLI 환각 탐지 ->
        Refiner의 자동 교정 -> 최종 정제된 JSON 반환

    루프 제한: 최대 MAX_VERIFICATION_LOOPS(2)회 반복
    강제 삭제: 2회 반복 후에도 환각이 남아있으면 해당 문장 강제 삭제

    Args:
        report_json: CareerAnalysisReport Pydantic 객체
        source_context: 원천 검색 데이터 컨텍스트
        company_name: 분석 대상 기업명
        model_provider: LLM 프로바이더
        job_id: Job UUID
        jobs_dict: 메모리 기반 상태 관리 딕셔너리

    Returns:
        (정제된 CareerAnalysisReport, 검증 로그 딕셔너리)
    """
    from backend.src.company.schemas.career_report import CareerAnalysisReport

    verification_log: dict[str, Any] = {"total_loops": 0, "loops": [], "final_action": "none"}

    current_report = report_json

    for loop_num in range(1, MAX_VERIFICATION_LOOPS + 1):
        logger.info(f"[{job_id}] NLI 검증 루프 {loop_num}/{MAX_VERIFICATION_LOOPS} 시작")

        # 현재 리포트를 JSON 문자열로 변환
        current_json_str = current_report.model_dump_json(ensure_ascii=False, indent=2)

        # --- Evaluator 호출 ---
        try:
            evaluation = await evaluate_report(
                draft_json=current_json_str,
                source_context=source_context,
                company_name=company_name,
                model_provider=model_provider,
            )
        except Exception as e:
            logger.error(f"[{job_id}] Evaluator 호출 실패 (루프 {loop_num}): {e}")
            verification_log["loops"].append({"loop": loop_num, "evaluator_error": str(e), "action": "skip"})
            break

        loop_log: dict[str, Any] = {
            "loop": loop_num,
            "has_hallucination": evaluation.has_hallucination,
            "findings_count": len(evaluation.findings),
            "findings": [f.model_dump() for f in evaluation.findings],
            "summary": evaluation.summary,
        }

        logger.info(
            f"[{job_id}] Evaluator 결과 (루프 {loop_num}): "
            f"환각 발견={evaluation.has_hallucination}, "
            f"지적 항목={len(evaluation.findings)}건"
        )

        # 환각이 없으면 루프 종료
        if not evaluation.has_hallucination or not evaluation.findings:
            loop_log["action"] = "pass"
            verification_log["loops"].append(loop_log)
            verification_log["final_action"] = "passed"
            logger.info(f"[{job_id}] NLI 검증 통과 (루프 {loop_num})")
            break

        # --- 마지막 루프: 강제 삭제 처리 ---
        if loop_num == MAX_VERIFICATION_LOOPS:
            logger.warning(
                f"[{job_id}] 최대 검증 루프 도달 ({MAX_VERIFICATION_LOOPS}회). "
                f"잔여 환각 {len(evaluation.findings)}건 강제 삭제 수행"
            )

            report_dict = current_report.model_dump()
            cleaned_dict, forced_deletions = force_delete_hallucinations(report_dict, evaluation.findings)

            current_report = CareerAnalysisReport.model_validate(cleaned_dict)

            loop_log["action"] = "force_delete"
            loop_log["forced_deletions"] = forced_deletions
            verification_log["loops"].append(loop_log)
            verification_log["final_action"] = "force_deleted"

            for fd in forced_deletions:
                logger.info(f"[{job_id}] {fd}")

            break

        # --- Refiner 호출 ---
        try:
            refinement = await refine_report(
                draft_json=current_json_str,
                evaluation=evaluation,
                source_context=source_context,
                company_name=company_name,
                model_provider=model_provider,
            )
        except Exception as e:
            logger.error(f"[{job_id}] Refiner 호출 실패 (루프 {loop_num}): {e}")
            loop_log["refiner_error"] = str(e)
            loop_log["action"] = "refiner_failed"
            verification_log["loops"].append(loop_log)
            break

        # Refiner 결과를 CareerAnalysisReport로 재검증
        try:
            current_report = CareerAnalysisReport.model_validate(refinement.refined_json)
        except Exception as e:
            logger.error(f"[{job_id}] Refiner 결과 스키마 검증 실패 (루프 {loop_num}): {e}")
            loop_log["refiner_validation_error"] = str(e)
            loop_log["action"] = "refiner_validation_failed"
            verification_log["loops"].append(loop_log)
            break

        loop_log["action"] = "refined"
        loop_log["changes_made"] = refinement.changes_made
        verification_log["loops"].append(loop_log)

        logger.info(f"[{job_id}] Refiner 교정 완료 (루프 {loop_num}): {len(refinement.changes_made)}건 수정")

        # 진행률 업데이트
        progress = 75 + int(5 * loop_num / MAX_VERIFICATION_LOOPS)
        jobs_dict[job_id]["progress"] = progress

    verification_log["total_loops"] = len(verification_log["loops"])

    return current_report, verification_log
