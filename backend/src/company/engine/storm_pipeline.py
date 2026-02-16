import asyncio
import logging
import os
import re
import traceback

from backend.src.common.config import AI_CONFIG
from backend.src.common.database.connection import AsyncDatabaseEngine
from backend.src.common.enums import ReportJobStatus
from backend.src.company.repositories.company_repository import CompanyRepository
from backend.src.company.repositories.report_job_repository import ReportJobRepository
from backend.src.company.services.quality_inspector import evaluate_report_quality
from backend.src.company.services.report_job_service import ReportJobService
from knowledge_storm import STORMWikiRunner, STORMWikiRunnerArguments

from .adapter import save_storm_result_to_db
from .builder import build_hybrid_rm, build_lm_configs
from .io import create_run_directory, find_topic_directory, write_run_metadata


logger = logging.getLogger(__name__)


async def run_storm_pipeline(
    job_id: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,  # 메모리 기반 상태 관리 (Optional)
    model_provider: str = "openai",
):
    logger.info(f"[{job_id}] 🚀 Starting STORM Pipeline for {company_name}")

    # [메모리 상태 업데이트] - UI polling용
    jobs_dict[job_id]["status"] = ReportJobStatus.PROCESSING.value
    jobs_dict[job_id]["progress"] = 10

    db_engine = AsyncDatabaseEngine()

    # ----------------------------------------------------------------
    # Phase 1: 작업 시작 상태 기록 (DB)
    # ----------------------------------------------------------------
    try:
        async with db_engine.get_session() as session:
            # Service 조립 (On-demand)
            job_repo = ReportJobRepository(session)
            job_service = ReportJobService(job_repo)

            # DB 상태 업데이트: PROCESSING
            await job_service.start_job(job_id)

            # Company ID 조회 (Engine 실행에 필요)
            company_repo = CompanyRepository(session)
            company = await company_repo.get_by_company_name(company_name)
            if not company:
                raise ValueError(f"Company '{company_name}' not found")
            company_id = company.id

    except Exception as e:
        logger.error(f"[{job_id}] Failed during initialization: {e}")
        # 초기화 실패는 즉시 종료
        jobs_dict[job_id]["status"] = ReportJobStatus.FAILED.value
        jobs_dict[job_id]["message"] = str(e)
        return

    # ----------------------------------------------------------------
    # Phase 2: STORM 엔진 실행 (Long-Running Task)
    # 주의: 이 구간에서는 DB 세션을 들고 있으면 안 됩니다. (Timeout 위험)
    # ----------------------------------------------------------------
    rm = None
    try:
        jobs_dict[job_id]["progress"] = 20

        # 1. Engine Build (Builder 활용 - 간소화됨)
        lm_configs = build_lm_configs(model_provider)
        rm = build_hybrid_rm(company_name=company_name, top_k=10)

        jobs_dict[job_id]["progress"] = 30

        # 2. IO & Runner 설정
        base_output_dir = os.path.join("results", "enterprise")
        output_dir = create_run_directory(base_output_dir, company_id, company_name, job_id)

        engine_args = STORMWikiRunnerArguments(
            output_dir=output_dir,
            max_conv_turn=3,
            max_perspective=3,
            search_top_k=10,
            max_thread_num=AI_CONFIG.get("storm_max_thread_num", 1),
        )

        runner = STORMWikiRunner(engine_args, lm_configs, rm)

        # 3. Blocking Run (스레드에서 실행하여 FastAPI 블로킹 방지)
        logger.info(f"[{job_id}] Running STORM core...")
        from datetime import date

        today_str = date.today().strftime("%Y-%m-%d")
        full_topic = f"{company_name} {topic} (기준일: {today_str})"
        # Windows 파일 시스템에서 허용되지 않는 문자 제거
        safe_topic = re.sub(r"[\\/:*?\"<>|]", " ", full_topic).strip()
        safe_topic = re.sub(r"\s+", " ", safe_topic)

        loop = asyncio.get_running_loop()

        # 메타데이터 기록
        write_run_metadata(output_dir, {"job_id": job_id, "topic": topic})

        # 실제 실행 (CPU Bound)
        await loop.run_in_executor(
            None,
            lambda: runner.run(
                topic=safe_topic,
                do_research=True,
                do_generate_outline=True,
                do_generate_article=True,
                do_polish_article=True,
            ),
        )

        # 마무리 작업
        runner.post_run()
        runner.summary()

        jobs_dict[job_id]["progress"] = 80

        # ----------------------------------------------------------------
        # Phase 2.5: 품질 검수 (Quality Inspection)
        # ----------------------------------------------------------------
        quality_result = None
        try:
            topic_dir = find_topic_directory(output_dir)
            if topic_dir:
                article_path = os.path.join(topic_dir, "storm_gen_article_polished.txt")
                if os.path.exists(article_path):
                    with open(article_path, encoding="utf-8") as f:
                        article_text = f.read()
                    if article_text.strip():
                        logger.info(f"[{job_id}] Running quality inspection...")
                        quality_result = evaluate_report_quality(article_text)
                        logger.info(f"[{job_id}] Quality grade: {quality_result.get('overall_grade', 'N/A')}")
                        jobs_dict[job_id]["quality_grade"] = quality_result.get("overall_grade", "N/A")
        except Exception as qe:
            logger.warning(f"[{job_id}] Quality inspection failed (non-blocking): {qe}")

        # ----------------------------------------------------------------
        # Phase 3: 결과 저장 및 종료 처리 (DB)
        # ----------------------------------------------------------------
        async with db_engine.get_session() as session:
            # Service 다시 조립 (새 세션)
            job_repo = ReportJobRepository(session)
            job_service = ReportJobService(job_repo)

            # [Adapter] 결과 저장 (Adapter 내부에서도 세션 관리가 필요할 수 있음)
            # 여기서는 Adapter가 session을 받도록 리팩토링한다고 가정하거나,
            # Adapter가 내부에서 해결하도록 해야 함.
            # (다음 단계 리팩토링 대상)
            report_id = await save_storm_result_to_db(
                session=session,  # 세션 주입 방식으로 변경 예정
                company_name=company_name,
                topic=topic,
                output_dir=output_dir,
                model_name=model_provider,
                meta_info={"job_id": job_id, "quality": quality_result},
            )
            if report_id is None:
                raise RuntimeError(f"Report DB 저장 실패: output_dir={output_dir}")
            # 성공 처리
            await job_service.complete_job(job_id)

            # 메모리 상태 업데이트
            jobs_dict[job_id]["status"] = ReportJobStatus.COMPLETED.value
            jobs_dict[job_id]["report_id"] = report_id
            jobs_dict[job_id]["progress"] = 100
            jobs_dict[job_id]["message"] = "완료"

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline Runtime Error: {e}")
        traceback.print_exc()

        # 에러 발생 시 DB에 기록 (Phase 3의 세션 연결 시도)
        try:
            async with db_engine.get_session() as session:
                job_repo = ReportJobRepository(session)
                job_service = ReportJobService(job_repo)
                await job_service.fail_job(job_id, str(e))
        except Exception as db_e:
            logger.critical(f"Failed to log error to DB: {db_e}")

        jobs_dict[job_id]["status"] = ReportJobStatus.FAILED.value
        jobs_dict[job_id]["message"] = str(e)
        jobs_dict[job_id]["progress"] = 0
    finally:
        if rm and hasattr(rm, "aclose"):
            try:
                await rm.aclose()
            except Exception as close_error:
                logger.warning(f"[{job_id}] Failed to close HybridRM: {close_error}")
