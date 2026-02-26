"""
Career AI Pipeline (하드코딩 페르소나 기반 기업 분석 파이프라인)

역할:
    - 기존 STORMWikiRunner의 동적 파이프라인(gen_perspectives, direct_gen_outline, refine_outline)을
      완전히 우회(Bypass)합니다.
    - 3가지 고정 페르소나의 하드코딩 쿼리 큐를 사용하여 검색을 수행합니다.
    - 검색 결과를 종합하여 LLM에게 순수 JSON 형태의 구조화된 보고서를 생성하도록 요청합니다.
    - Pydantic 스키마 검증 + JSON 파싱 방어 로직 + 재시도(Retry) 로직을 적용합니다.

Happy Path:
    1. 고정 페르소나 쿼리 큐 로드 → 2. 쿼리 후처리(기업명 prefix) →
    3. HybridRM 검색 → 4. LLM JSON 생성 → 5. 파싱/검증 → 6. DB 적재 (COMPLETED)
    + 중간 컨텍스트 추적(context_trace.json) 및 출처 포맷팅(url_to_unified_index)
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import date, datetime
from typing import Any

from backend.src.common.config import AI_CONFIG
from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.enums import ReportJobStatus
from backend.src.company.engine.evaluator import evaluate_report
from backend.src.company.engine.ingestion import schedule_ingestion
from backend.src.company.engine.intermediate_refinement import expand_queries, refine_search_results
from backend.src.company.engine.json_utils import build_retry_prompt, safe_parse_career_report
from backend.src.company.engine.personas import (
    ALL_PERSONAS,
    FINAL_SYNTHESIS_PROMPT,
    PHASE1_SYSTEM_PROMPT,
    PHASE2_SYSTEM_PROMPT,
    PHASE3_SYSTEM_PROMPT,
    PHASE_PERSONA_MAP,
    Persona,
    build_query_queue,
)
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
# LLM 입력 컨텍스트 최대 글자 수 (토큰 초과 방어)
MAX_CONTEXT_CHARS = 50_000


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

    # JOBS dict에 없는 경우(관리자 승인 경로 등) 안전하게 초기화
    jobs_dict.setdefault(
        job_id,
        {"status": ReportJobStatus.PENDING.value, "progress": 0, "message": "파이프라인 초기화 중", "report_id": None},
    )

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

        # 쿼리 후처리: 기업명 prefix + 길이 제한
        original_queries = query_items  # 후처리 전 원본 보존
        processed_queries = _post_process_queries(query_items, company_name)
        for pq in processed_queries:
            logger.info(f"[{job_id}] [QueryPostProcess] [{pq['tag']}] {pq['persona']}: {pq['query']}")

        jobs_dict[job_id]["progress"] = 15

        # ================================================================
        # Phase 3: Sequential RAG — 3단계 순차 검색-생성-NLI 검증
        # ================================================================
        # HybridRM 1회 생성, 3개 Phase에서 재사용
        from .builder import build_hybrid_rm

        rm = build_hybrid_rm(company_name=company_name, top_k=10)

        all_search_results: list[dict] = []
        phase_logs: dict[str, dict[str, Any]] = {}
        phase_context_texts: dict[str, str] = {}
        phase_truncation_infos: dict[str, dict[str, Any]] = {}
        search_results_by_persona: dict[str, list[dict]] = {}

        # --- Phase 3A: 기초 팩트 (company_overview) ---
        phase1_report, ctx1, trunc1, vlog1, results1 = await _run_single_phase(
            phase_num=1,
            phase_name="기초 팩트",
            system_prompt=PHASE1_SYSTEM_PROMPT,
            processed_queries=processed_queries,
            rm=rm,
            target_personas=PHASE_PERSONA_MAP[1],
            company_name=company_name,
            topic=topic,
            model_provider=model_provider,
            job_id=job_id,
            jobs_dict=jobs_dict,
            chaining_context=None,
            progress_range=(15, 35),
        )
        all_search_results.extend(results1)
        phase_logs["phase_1"] = vlog1
        phase_context_texts["phase_1"] = ctx1
        phase_truncation_infos["phase_1"] = trunc1
        for pq in processed_queries:
            if pq["persona"] in {p.name for p in PHASE_PERSONA_MAP[1]}:
                persona_name = pq["persona"]
                if persona_name not in search_results_by_persona:
                    search_results_by_persona[persona_name] = []
        # Phase 1 검색 결과를 persona별로 기록
        for r in results1:
            for p in PHASE_PERSONA_MAP[1]:
                if p.name not in search_results_by_persona:
                    search_results_by_persona[p.name] = []
                search_results_by_persona[p.name].append(r)

        # --- Phase 3B: 체이닝 컨텍스트 구성 (Phase 1 → Phase 2) ---
        chaining_ctx_1 = _build_chaining_context(phase1_report, "기초 팩트", ["company_overview"])

        # --- Phase 3C: 심층 분석 (corporate_culture + swot_analysis) ---
        phase2_report, ctx2, trunc2, vlog2, results2 = await _run_single_phase(
            phase_num=2,
            phase_name="심층 분석",
            system_prompt=PHASE2_SYSTEM_PROMPT,
            processed_queries=processed_queries,
            rm=rm,
            target_personas=PHASE_PERSONA_MAP[2],
            company_name=company_name,
            topic=topic,
            model_provider=model_provider,
            job_id=job_id,
            jobs_dict=jobs_dict,
            chaining_context=chaining_ctx_1,
            progress_range=(35, 60),
        )
        all_search_results.extend(results2)
        phase_logs["phase_2"] = vlog2
        phase_context_texts["phase_2"] = ctx2
        phase_truncation_infos["phase_2"] = trunc2
        for r in results2:
            for p in PHASE_PERSONA_MAP[2]:
                if p.name not in search_results_by_persona:
                    search_results_by_persona[p.name] = []
                search_results_by_persona[p.name].append(r)

        # --- Phase 3D: 체이닝 컨텍스트 구성 (Phase 1+2 → Phase 3) ---
        chaining_ctx_2 = _build_chaining_context(phase2_report, "심층 분석", ["corporate_culture", "swot_analysis"])
        # Phase 1 + Phase 2 검증 결과를 모두 주입
        combined_chaining = chaining_ctx_1 + "\n\n" + chaining_ctx_2

        # --- Phase 3E: 면접 파생 (interview_preparation) ---
        phase3_report, ctx3, trunc3, vlog3, results3 = await _run_single_phase(
            phase_num=3,
            phase_name="면접 파생",
            system_prompt=PHASE3_SYSTEM_PROMPT,
            processed_queries=processed_queries,
            rm=rm,
            target_personas=PHASE_PERSONA_MAP[3],
            company_name=company_name,
            topic=topic,
            model_provider=model_provider,
            job_id=job_id,
            jobs_dict=jobs_dict,
            chaining_context=combined_chaining,
            progress_range=(60, 80),
        )
        all_search_results.extend(results3)
        phase_logs["phase_3"] = vlog3
        phase_context_texts["phase_3"] = ctx3
        phase_truncation_infos["phase_3"] = trunc3
        for r in results3:
            for p in PHASE_PERSONA_MAP[3]:
                if p.name not in search_results_by_persona:
                    search_results_by_persona[p.name] = []
                search_results_by_persona[p.name].append(r)

        # ================================================================
        # Phase 4: 결과 병합
        # ================================================================
        report_json = _merge_phase_results(phase1_report, phase2_report, phase3_report)

        # 통합 검증 로그 구성
        verification_log: dict[str, Any] = {
            "phases": phase_logs,
            "total_loops": sum(v.get("total_loops", 0) for v in phase_logs.values()),
        }

        jobs_dict[job_id]["progress"] = 85

        # ================================================================
        # Phase 5: 결과 저장 및 상태 업데이트
        # ================================================================

        # DB에 저장
        report_content_json = report_json.model_dump_json(ensure_ascii=False, indent=2)

        # output_dir 생성 (메타데이터 및 로그 저장용)
        base_output_dir = "results"
        output_dir = create_run_directory(base_output_dir, company_id, company_name, job_id)

        # 메타데이터 기록
        write_run_metadata(
            output_dir,
            {
                "job_id": job_id,
                "topic": topic,
                "pipeline": "career_pipeline_v3.0",
                "architecture": "3-phase-sequential-rag-with-refinement",
                "personas": [p.name for p in ALL_PERSONAS],
                "total_queries": len(processed_queries),
                "total_search_results": len(all_search_results),
                "model_provider": model_provider,
                "verification_loops": verification_log.get("total_loops", 0),
                "phases": {
                    "phase_1": {"name": "기초 팩트", "sections": ["company_overview"]},
                    "phase_2": {"name": "심층 분석", "sections": ["corporate_culture", "swot_analysis"]},
                    "phase_3": {"name": "면접 파생", "sections": ["interview_preparation"]},
                },
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

        # 검색 로그 저장 (Phase별 구조 포함)
        search_log_path = os.path.join(output_dir, "search_log.json")
        phase_queries_map: dict[str, list[dict]] = {}
        for phase_id, personas in PHASE_PERSONA_MAP.items():
            persona_names = {p.name for p in personas}
            phase_queries_map[f"phase_{phase_id}"] = [pq for pq in processed_queries if pq["persona"] in persona_names]

        with open(search_log_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "original_queries": original_queries,
                    "processed_queries": processed_queries,
                    "results_count_by_persona": {k: len(v) for k, v in search_results_by_persona.items()},
                    "phases": {
                        pid: {
                            "queries": [pq["query"] for pq in pqs],
                            "results_count": len([r for r in all_search_results]),
                        }
                        for pid, pqs in phase_queries_map.items()
                    },
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        # 컨텍스트 추적 로그 저장 (Phase별 context_text 병합)
        combined_context_text = "\n\n".join(phase_context_texts.values())
        combined_truncation_info = {
            "phases": phase_truncation_infos,
            "total_original_length": sum(t.get("original_length", 0) for t in phase_truncation_infos.values()),
            "total_final_length": sum(t.get("final_length", 0) for t in phase_truncation_infos.values()),
        }
        _write_context_trace(
            output_dir=output_dir,
            company_name=company_name,
            job_id=job_id,
            processed_queries=processed_queries,
            search_results_by_persona=search_results_by_persona,
            context_text=combined_context_text,
            truncation_info=combined_truncation_info,
            all_search_results=all_search_results,
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
                references_data=_format_references_for_frontend(all_search_results),
                conversation_log={
                    "pipeline": "career_pipeline_v3.0",
                    "architecture": "3-phase-sequential-rag-with-refinement",
                    "search_queries": processed_queries,
                    "verification_log": verification_log,
                },
                model_name=model_provider,
                meta_info={"job_id": job_id, "file_path": output_dir, "pipeline_version": "v3.0"},
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
    쿼리 후처리: 기업명 prefix 추가 및 길이 제한만 수행합니다.

    카테고리 태그(재무, 인재상 등) 강제 병합 로직은 제거되었습니다.
    시스템 프롬프트에 정의된 원본 쿼리 문자열만 온전히 전달합니다.

    Args:
        query_items: build_query_queue의 결과
        company_name: 기업명

    Returns:
        기업명이 보강된 쿼리 리스트
    """
    processed = []
    for item in query_items:
        query = item["query"]
        persona = item["persona"]
        tag = item["tag"]

        # 기업명이 쿼리에 없으면 추가
        if company_name not in query:
            query = f"{company_name} {query}"

        # 길이 제한
        query = query[:200].strip()

        processed.append({"persona": persona, "query": query, "tag": tag})

    return processed


def _build_llm_context(
    search_results_by_persona: dict[str, list[dict]], company_name: str, target_personas: list[Persona] | None = None
) -> tuple[str, dict[str, Any]]:
    """
    페르소나별 검색 결과를 LLM 컨텍스트 문자열로 변환합니다.

    MAX_CONTEXT_CHARS 글자 수 기반 truncation을 적용하여 토큰 초과를 방어합니다.

    Args:
        search_results_by_persona: 페르소나별 검색 결과
        company_name: 기업명
        target_personas: 컨텍스트에 포함할 페르소나 리스트 (None이면 ALL_PERSONAS)

    Returns:
        (LLM에게 전달할 컨텍스트 문자열, truncation 메타데이터 dict)
    """
    personas = target_personas if target_personas is not None else ALL_PERSONAS

    sections = []
    snippets_per_persona: dict[str, int] = {}

    for persona in personas:
        results = search_results_by_persona.get(persona.name, [])
        section_lines = [
            f"\n## [{persona.name}] 수집 데이터",
            f"역할: {persona.role}",
            f"검색 결과: {len(results)}건",
            "",
        ]

        if not results:
            section_lines.append("(검색 결과 없음)")
            snippets_per_persona[persona.name] = 0
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

            snippets_per_persona[persona.name] = count

        sections.append("\n".join(section_lines))

    header = f"# {company_name} 기업 분석을 위한 수집 데이터\n"
    full_text = header + "\n\n".join(sections)

    # Truncation: MAX_CONTEXT_CHARS 글자 수 기반 절삭
    original_length = len(full_text)
    truncated = False
    if original_length > MAX_CONTEXT_CHARS:
        # 줄 단위로 절삭하여 문장이 중간에 끊기지 않도록 함
        cut_text = full_text[:MAX_CONTEXT_CHARS]
        last_newline = cut_text.rfind("\n")
        full_text = cut_text[:last_newline] if last_newline > MAX_CONTEXT_CHARS * 0.8 else cut_text
        full_text += "\n\n[... 텍스트 절삭됨: 원본 길이 초과 ...]"
        truncated = True
        logger.warning(f"LLM 컨텍스트 절삭: {original_length} -> {len(full_text)} 글자")

    truncation_info: dict[str, Any] = {
        "original_length": original_length,
        "final_length": len(full_text),
        "truncated": truncated,
        "max_context_chars": MAX_CONTEXT_CHARS,
        "snippets_per_persona": snippets_per_persona,
    }

    return full_text, truncation_info


def _build_refined_llm_context(
    refined_answers: dict[str, str],
    expanded_queries: list[dict[str, str]],
    search_results_by_persona: dict[str, list[dict]],
    company_name: str,
    target_personas: list[Persona] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    중간 정제(AnswerQuestion)된 답변을 LLM 컨텍스트 문자열로 변환합니다.

    원시 스니펫 대신 경량 LLM이 추출/압축한 핵심 답변을 사용하여
    정보 밀도를 높이고 노이즈를 줄입니다.

    Args:
        refined_answers: {query -> 정제된 답변 텍스트}
        expanded_queries: 확장된 쿼리 리스트
        search_results_by_persona: 페르소나별 검색 결과 (출처 URL 추출용)
        company_name: 기업명
        target_personas: 컨텍스트에 포함할 페르소나 리스트

    Returns:
        (LLM에게 전달할 컨텍스트 문자열, truncation 메타데이터 dict)
    """
    personas = target_personas if target_personas is not None else ALL_PERSONAS

    sections = []
    refined_per_persona: dict[str, int] = {}

    for persona in personas:
        # 해당 페르소나의 쿼리/답변만 필터링
        persona_queries = [pq for pq in expanded_queries if pq["persona"] == persona.name]
        results = search_results_by_persona.get(persona.name, [])

        section_lines = [
            f"\n## [{persona.name}] 정제된 분석 데이터",
            f"역할: {persona.role}",
            f"확장 쿼리 수: {len(persona_queries)}개 | 검색 결과: {len(results)}건",
            "",
        ]

        valid_count = 0
        seen_answers: set[str] = set()

        for pq in persona_queries:
            query = pq["query"]
            answer = refined_answers.get(query, "")

            if not answer or answer in seen_answers:
                continue

            seen_answers.add(answer)
            section_lines.append(f"### Q: {query}")
            section_lines.append(f"{answer}")
            section_lines.append("")
            valid_count += 1

        if valid_count == 0:
            section_lines.append("(정제된 답변 없음 - 원시 검색 결과 폴백)")
            # Fallback: 원시 스니펫에서 상위 10개 추출
            seen_snippets: set[str] = set()
            fallback_count = 0
            for r in results:
                for snippet in r.get("snippets", []):
                    snippet_key = snippet[:100] if snippet else ""
                    if snippet_key in seen_snippets or not snippet:
                        continue
                    seen_snippets.add(snippet_key)
                    title = r.get("title", "")
                    url = r.get("url", "")
                    source_info = f"[출처: {title}]" if title else ""
                    if url:
                        source_info += f" ({url})"
                    section_lines.append(f"- {snippet.strip()} {source_info}")
                    fallback_count += 1
                    if fallback_count >= 10:
                        break
                if fallback_count >= 10:
                    break

        refined_per_persona[persona.name] = valid_count
        sections.append("\n".join(section_lines))

    header = f"# {company_name} 기업 분석을 위한 정제된 데이터\n"
    full_text = header + "\n\n".join(sections)

    # Truncation
    original_length = len(full_text)
    truncated = False
    if original_length > MAX_CONTEXT_CHARS:
        cut_text = full_text[:MAX_CONTEXT_CHARS]
        last_newline = cut_text.rfind("\n")
        full_text = cut_text[:last_newline] if last_newline > MAX_CONTEXT_CHARS * 0.8 else cut_text
        full_text += "\n\n[... 텍스트 절삭됨: 원본 길이 초과 ...]"
        truncated = True
        logger.warning(f"정제 컨텍스트 절삭: {original_length} -> {len(full_text)} 글자")

    truncation_info: dict[str, Any] = {
        "original_length": original_length,
        "final_length": len(full_text),
        "truncated": truncated,
        "max_context_chars": MAX_CONTEXT_CHARS,
        "refined_per_persona": refined_per_persona,
        "pipeline_version": "v3.0-refined",
    }

    return full_text, truncation_info


def _build_final_prompt(company_name: str, topic: str, context_text: str, chaining_context: str | None = None) -> str:
    """
    최종 LLM 프롬프트를 조합합니다.

    Args:
        company_name: 기업명
        topic: 분석 주제
        context_text: 검색 결과 컨텍스트
        chaining_context: 이전 Phase 검증 결과 (Sequential RAG 체이닝용)

    Returns:
        LLM에게 전달할 최종 프롬프트
    """
    today_str = date.today().strftime("%Y-%m-%d")

    parts = [f"분석 대상 기업: {company_name}", f"분석 주제: {topic}", f"기준일: {today_str}", ""]

    # Sequential RAG 체이닝: 이전 Phase 검증 결과 주입
    if chaining_context:
        parts.append("## 이전 분석 단계 검증 결과")
        parts.append(chaining_context)
        parts.append("")

    parts.append("아래의 수집 데이터를 종합하여 JSON 분석 보고서를 생성하십시오.")
    parts.append("")
    parts.append(context_text)

    return "\n".join(parts)


async def _call_llm(prompt: str, model_provider: str = "openai", system_prompt: str | None = None) -> str:
    """
    LLM을 호출하여 응답을 반환합니다.

    Args:
        prompt: 전체 프롬프트 (시스템 + 사용자)
        model_provider: 'openai' 또는 'gemini'
        system_prompt: 시스템 프롬프트 (None이면 FINAL_SYNTHESIS_PROMPT 사용)

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

    effective_system_prompt = system_prompt if system_prompt is not None else FINAL_SYNTHESIS_PROMPT
    messages = [{"role": "system", "content": effective_system_prompt}, {"role": "user", "content": prompt}]

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
    검색 결과에서 참고 URL 목록을 추출합니다. (레거시 형식)
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


def _format_references_for_frontend(all_search_results: list[dict]) -> dict[str, Any]:
    """
    검색 결과를 프론트엔드 buildCitationDict()가 기대하는 형식으로 변환합니다.

    출력 형식:
        {
            "url_to_unified_index": {"https://example.com": 1, ...},
            "url_to_info": {
                "https://example.com": {"title": "...", "snippets": ["..."]},
                ...
            }
        }
    """
    url_to_unified_index: dict[str, int] = {}
    url_to_info: dict[str, dict[str, Any]] = {}
    index_counter = 1

    for r in all_search_results:
        url = r.get("url", "")
        if not url:
            continue

        title = r.get("title", "")
        snippets = r.get("snippets", [])

        if url not in url_to_unified_index:
            url_to_unified_index[url] = index_counter
            url_to_info[url] = {"title": title or url, "snippets": [s for s in snippets if s] if snippets else []}
            index_counter += 1
        else:
            # 동일 URL의 추가 스니펫은 병합
            existing = url_to_info[url]
            if snippets:
                existing_set = set(existing["snippets"])
                for s in snippets:
                    if s and s not in existing_set:
                        existing["snippets"].append(s)

    return {"url_to_unified_index": url_to_unified_index, "url_to_info": url_to_info}


def _write_context_trace(
    output_dir: str,
    company_name: str,
    job_id: str,
    processed_queries: list[dict[str, str]],
    search_results_by_persona: dict[str, list[dict]],
    context_text: str,
    truncation_info: dict[str, Any],
    all_search_results: list[dict],
) -> None:
    """
    LLM에 주입된 중간 컨텍스트와 출처 리스트를 context_trace.json에 기록합니다.

    Python 내장 json 모듈만 사용합니다 (외부 로깅 프레임워크 금지).
    검색 결과가 0건인 엣지 케이스도 빈 배열과 "정보 없음"으로 안전하게 처리합니다.

    Args:
        output_dir: 결과 저장 디렉토리
        company_name: 기업명
        job_id: Job UUID
        processed_queries: 후처리된 쿼리 리스트
        search_results_by_persona: 페르소나별 검색 결과
        context_text: LLM에 전달된 컨텍스트 문자열
        truncation_info: truncation 메타데이터
        all_search_results: 전체 검색 결과 리스트
    """
    try:
        # 페르소나별 쿼리 그룹핑
        queries_by_persona: dict[str, list[str]] = {}
        for pq in processed_queries:
            persona = pq["persona"]
            if persona not in queries_by_persona:
                queries_by_persona[persona] = []
            queries_by_persona[persona].append(pq["query"])

        # 페르소나별 raw context 추출 (컨텍스트 전체를 페르소나 단위로 분리)
        raw_context_by_persona: dict[str, str] = {}
        for persona in ALL_PERSONAS:
            results = search_results_by_persona.get(persona.name, [])
            if not results:
                raw_context_by_persona[persona.name] = "정보 없음"
            else:
                snippets_text = []
                for r in results:
                    for s in r.get("snippets", []):
                        if s:
                            snippets_text.append(s.strip())
                raw_context_by_persona[persona.name] = "\n".join(snippets_text) if snippets_text else "정보 없음"

        # 출처 리스트 구성
        source_list: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for persona_name, results in search_results_by_persona.items():
            for r in results:
                url = r.get("url", "")
                title = r.get("title", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    source_list.append({"url": url, "title": title, "persona": persona_name})

        trace_data = {
            "company_name": company_name,
            "job_id": job_id,
            "timestamp": datetime.now().isoformat(),
            "queries": queries_by_persona,
            "raw_context": raw_context_by_persona,
            "source_list": source_list if source_list else [],
            "context_stats": truncation_info,
        }

        trace_path = os.path.join(output_dir, "context_trace.json")
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Context trace 저장 완료: {trace_path}")

    except Exception as e:
        # Trace Logger 실패는 파이프라인을 중단시키지 않음
        logger.warning(f"Context trace 저장 실패 (non-blocking): {e}")


# ============================================================
# Sequential RAG 헬퍼 함수
# ============================================================

# Context Starvation 메시지 상수
CONTEXT_STARVATION_MSG = "이전 분석 단계에서 데이터 부족으로 검증된 데이터가 충분하지 않습니다. 본 단계에서는 검색 결과만을 기반으로 분석을 수행하십시오."


def _is_section_starved(section_dict: dict[str, Any]) -> bool:
    """
    섹션의 모든 필드가 기본값('정보 부족')인지 판별합니다.

    Args:
        section_dict: 섹션 딕셔너리

    Returns:
        모든 필드가 기본값이면 True
    """
    for value in section_dict.values():
        if isinstance(value, str):
            if "정보 부족" not in value and value.strip():
                return False
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and "정보 부족" not in item and item.strip():
                    return False
        elif isinstance(value, dict):
            if not _is_section_starved(value):
                return False
    return True


def _build_chaining_context(report: Any | None, phase_name: str, section_keys: list[str]) -> str:
    """
    검증 완료된 Phase 결과를 다음 Phase 프롬프트에 주입할 JSON 문자열로 변환합니다.

    Context Starvation 방어: 검증 후 해당 섹션의 모든 필드가 기본값이면
    starvation 메시지를 반환합니다.

    Args:
        report: CareerAnalysisReport 객체 (None 허용, Null Safe)
        phase_name: Phase 표시명 (예: "기초 팩트")
        section_keys: 추출할 섹션 키 리스트 (예: ["company_overview"])

    Returns:
        JSON 문자열 또는 starvation 메시지
    """
    if report is None:
        return f"[{phase_name}] {CONTEXT_STARVATION_MSG}"

    try:
        report_dict = report.model_dump()
        result = {}
        all_starved = True

        for key in section_keys:
            section_data = report_dict.get(key, {})
            result[key] = section_data
            if not _is_section_starved(section_data):
                all_starved = False

        if all_starved:
            return f"[{phase_name}] {CONTEXT_STARVATION_MSG}"

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning(f"Chaining context 생성 실패 ({phase_name}): {e}")
        return f"[{phase_name}] {CONTEXT_STARVATION_MSG}"


def _merge_phase_results(phase1_report: Any | None, phase2_report: Any | None, phase3_report: Any | None) -> Any:
    """
    3개 Phase의 부분 CareerAnalysisReport를 최종 1개로 병합합니다.

    각 Phase에서 해당 섹션만 추출하여 통합합니다.
    실패한 Phase(None)의 섹션은 기본값(정보 부족)으로 채워집니다.

    Args:
        phase1_report: Phase 1 결과 (company_overview)
        phase2_report: Phase 2 결과 (corporate_culture, swot_analysis)
        phase3_report: Phase 3 결과 (interview_preparation)

    Returns:
        병합된 CareerAnalysisReport 객체
    """
    from backend.src.company.schemas.career_report import CareerAnalysisReport

    merged: dict[str, Any] = {}

    # Phase 1: company_overview
    if phase1_report is not None:
        merged["company_overview"] = phase1_report.model_dump().get("company_overview", {})

    # Phase 2: corporate_culture + swot_analysis
    if phase2_report is not None:
        p2_dict = phase2_report.model_dump()
        merged["corporate_culture"] = p2_dict.get("corporate_culture", {})
        merged["swot_analysis"] = p2_dict.get("swot_analysis", {})

    # Phase 3: interview_preparation
    if phase3_report is not None:
        merged["interview_preparation"] = phase3_report.model_dump().get("interview_preparation", {})

    return CareerAnalysisReport.model_validate(merged)


async def _run_single_phase(
    phase_num: int,
    phase_name: str,
    system_prompt: str,
    processed_queries: list[dict[str, str]],
    rm: Any,
    target_personas: list[Persona],
    company_name: str,
    topic: str,
    model_provider: str,
    job_id: str,
    jobs_dict: dict[str, dict[str, Any]],
    chaining_context: str | None = None,
    progress_range: tuple[int, int] = (0, 100),
) -> tuple[Any | None, str, dict[str, Any], dict[str, Any], list[dict]]:
    """
    단일 Phase의 쿼리확장-검색-중간정제-생성-NLI 검증 사이클을 실행합니다.

    v3.0 변경사항:
        - QuestionToQuery: 각 질문을 3~5개 다각화 쿼리로 확장
        - AnswerQuestion: 검색 결과를 경량 LLM으로 1차 정제 후 최종 LLM에 주입
        - 비동기 DB 적재: 검색 결과를 external_informations 테이블에 백그라운드 적재

    Args:
        phase_num: Phase 번호 (1, 2, 3)
        phase_name: Phase 표시명
        system_prompt: Phase 전용 시스템 프롬프트
        processed_queries: 전체 후처리된 쿼리 리스트
        rm: HybridRM 인스턴스
        target_personas: 이 Phase에서 사용할 페르소나 리스트
        company_name: 기업명
        topic: 분석 주제
        model_provider: LLM 프로바이더
        job_id: Job UUID
        jobs_dict: 메모리 기반 상태 관리 딕셔너리
        chaining_context: 이전 Phase 검증 결과 (Sequential RAG 체이닝)
        progress_range: 이 Phase에 할당된 진행률 범위 (start, end)

    Returns:
        (verified_report, context_text, truncation_info, verification_log, phase_search_results)
    """
    logger.info(f"[{job_id}] === Phase {phase_num} ({phase_name}) 시작 ===")
    progress_start, progress_end = progress_range
    target_persona_names = {p.name for p in target_personas}

    # ---- 1. 해당 Phase 페르소나 쿼리만 필터링 ----
    phase_queries = [pq for pq in processed_queries if pq["persona"] in target_persona_names]
    logger.info(f"[{job_id}] Phase {phase_num} 원본 쿼리: {len(phase_queries)}개")

    # ---- 1.5. QuestionToQuery: 쿼리 다각화 (Query Expansion) ----
    expanded_queries: list[dict[str, str]] = []
    for pq in phase_queries:
        original_query = pq["query"]
        persona_name = pq["persona"]
        tag = pq["tag"]

        try:
            sub_queries = await expand_queries(original_query, company_name, model_provider)
            for sq in sub_queries:
                expanded_queries.append({"persona": persona_name, "query": sq, "tag": tag})
            logger.info(f"[{job_id}] Phase {phase_num} 쿼리 확장: '{original_query}' -> {len(sub_queries)}개")
        except Exception as e:
            logger.warning(f"[{job_id}] Phase {phase_num} 쿼리 확장 실패 (fallback): {original_query} - {e}")
            expanded_queries.append(pq)  # fallback: 원본 쿼리 유지

    logger.info(f"[{job_id}] Phase {phase_num} 쿼리 확장 완료: {len(phase_queries)}개 -> {len(expanded_queries)}개")

    # 진행률: 쿼리 확장 완료
    expansion_progress = progress_start + int((progress_end - progress_start) * 0.1)
    jobs_dict[job_id]["progress"] = expansion_progress

    # ---- 2. HybridRM 검색 실행 (확장된 쿼리로) ----
    search_results_by_persona: dict[str, list[dict]] = {}
    search_results_by_query: dict[str, list[dict]] = {}
    phase_search_results: list[dict] = []
    loop = asyncio.get_running_loop()

    for i, pq in enumerate(expanded_queries):
        persona_name = pq["persona"]
        query = pq["query"]

        try:
            results = await loop.run_in_executor(None, lambda q=query: rm.forward(q, exclude_urls=[]))

            if persona_name not in search_results_by_persona:
                search_results_by_persona[persona_name] = []

            if query not in search_results_by_query:
                search_results_by_query[query] = []

            if results:
                search_results_by_persona[persona_name].extend(results)
                search_results_by_query[query].extend(results)
                phase_search_results.extend(results)
                logger.info(
                    f"[{job_id}] Phase {phase_num} 쿼리 [{i + 1}/{len(expanded_queries)}] '{query}': {len(results)}건"
                )
            else:
                logger.warning(
                    f"[{job_id}] Phase {phase_num} 쿼리 [{i + 1}/{len(expanded_queries)}] '{query}': 결과 없음 (skip)"
                )

        except Exception as e:
            logger.warning(f"[{job_id}] Phase {phase_num} 쿼리 검색 실패 (non-blocking): {query} - {e}")
            continue

        # 진행률 업데이트 (검색 구간: 10%~35%)
        search_progress = expansion_progress + int(
            (progress_end - progress_start) * 0.25 * (i + 1) / max(len(expanded_queries), 1)
        )
        jobs_dict[job_id]["progress"] = search_progress

    logger.info(f"[{job_id}] Phase {phase_num} 검색 완료: {len(phase_search_results)}건")

    # ---- 2.5. 비동기 DB 적재 (백그라운드, non-blocking) ----
    schedule_ingestion(phase_search_results, company_name, job_id)

    # ---- 3. AnswerQuestion: 중간 정제 (Map-Reduce) ----
    refined_answers = await refine_search_results(
        query_items=expanded_queries,
        search_results_by_query=search_results_by_query,
        company_name=company_name,
        model_provider=model_provider,
    )

    # 진행률: 중간 정제 완료
    refinement_progress = progress_start + int((progress_end - progress_start) * 0.45)
    jobs_dict[job_id]["progress"] = refinement_progress

    logger.info(
        f"[{job_id}] Phase {phase_num} 중간 정제 완료: "
        f"{sum(1 for v in refined_answers.values() if v)}/"
        f"{len(refined_answers)}개 유효 답변"
    )

    # ---- 3.5. 정제된 답변 기반 LLM 컨텍스트 빌드 ----
    context_text, truncation_info = _build_refined_llm_context(
        refined_answers=refined_answers,
        expanded_queries=expanded_queries,
        search_results_by_persona=search_results_by_persona,
        company_name=company_name,
        target_personas=target_personas,
    )
    base_prompt = _build_final_prompt(company_name, topic, context_text, chaining_context)

    # ---- 4. LLM 호출 + 파싱 (재시도 포함) ----
    report_json = None
    last_error = None
    prompt = base_prompt

    for attempt in range(1, MAX_LLM_RETRIES + 2):
        logger.info(f"[{job_id}] Phase {phase_num} LLM 호출 시도 {attempt}/{MAX_LLM_RETRIES + 1}")

        raw_response = await _call_llm(prompt, model_provider, system_prompt)
        report, error = safe_parse_career_report(raw_response)

        if report is not None:
            report_json = report
            logger.info(f"[{job_id}] Phase {phase_num} JSON 파싱 성공 (시도 {attempt})")
            break

        last_error = error
        logger.warning(f"[{job_id}] Phase {phase_num} JSON 파싱 실패 (시도 {attempt}): {error}")

        if attempt <= MAX_LLM_RETRIES:
            prompt = build_retry_prompt(base_prompt, error or "Unknown error")
        else:
            logger.error(f"[{job_id}] Phase {phase_num} 최대 재시도 횟수 초과.")

    llm_progress = progress_start + int((progress_end - progress_start) * 0.7)
    jobs_dict[job_id]["progress"] = llm_progress

    # ---- 5. NLI 검증 루프 ----
    verification_log: dict[str, Any] = {}
    if report_json is not None:
        # NLI source context에 chaining_context도 포함하여 이전 Phase 참조 문장의 환각 오판 방지
        nli_source_context = context_text
        if chaining_context:
            nli_source_context = f"## 이전 분석 단계 검증 결과\n{chaining_context}\n\n{context_text}"

        report_json, verification_log = await _run_verification_loop(
            report_json=report_json,
            source_context=nli_source_context,
            company_name=company_name,
            model_provider=model_provider,
            job_id=job_id,
            jobs_dict=jobs_dict,
        )
        logger.info(
            f"[{job_id}] Phase {phase_num} NLI 검증 루프 완료: "
            f"{verification_log.get('total_loops', 0)}회 반복, "
            f"결과: {verification_log.get('final_action', 'none')}"
        )
    else:
        logger.warning(f"[{job_id}] Phase {phase_num} LLM 생성 실패. NLI 검증 건너뜀. 오류: {last_error}")

    jobs_dict[job_id]["progress"] = progress_end
    logger.info(f"[{job_id}] === Phase {phase_num} ({phase_name}) 완료 ===")

    return report_json, context_text, truncation_info, verification_log, phase_search_results


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
            logger.error(f"[{job_id}] Evaluator 호출/파싱 실패 (루프 {loop_num}): {e}")
            verification_log["loops"].append({"loop": loop_num, "evaluator_error": str(e), "action": "error"})
            verification_log["final_action"] = "error"
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
        # NOTE: or -> and 버그 픽스. has_hallucination=True이면서 findings=[]인 엣지 케이스 방어
        if not evaluation.has_hallucination and not evaluation.findings:
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
