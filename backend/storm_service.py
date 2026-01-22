"""
STORM Pipeline Service for Backend (v4.1 - Engine Integrated)
Task ID: PHASE-3-Backend-Integration
Refactored:
- Delegated core logic to 'src.engine' package (Builder, IO, Adapter)
- Simplified orchestration logic
- Maintains Async/Non-blocking execution architecture
- Fixed: Moved datetime import to top
"""

import asyncio
import logging
import os
import traceback
from datetime import datetime

# Knowledge STORM Imports (Only Runner needed)
from knowledge_storm import STORMWikiRunner, STORMWikiRunnerArguments

# Common Configuration
from src.common.config import JOB_STATUS
from src.database import AsyncDatabaseEngine
from src.database.repositories import CompanyRepository

# Engine Components (New Architecture)
from src.engine import (
    build_hybrid_rm,
    build_lm_configs,
    create_run_directory,
    save_storm_result_to_db,
    write_run_metadata,
)

logger = logging.getLogger(__name__)


async def run_storm_pipeline(
    job_id: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,
    model_provider: str = "openai",
):
    """
    Background Task: Orchestrates the STORM pipeline using src.engine components.

    Flow:
    1. Resolve Company ID (DB)
    2. Build Engine Components (Configs, RM) via Builder
    3. Prepare Workspace (IO) via IO module
    4. Run STORM (Blocking) in ThreadPool
    5. Save Results (DB) via Adapter
    """
    logger.info(f"[{job_id}] 🚀 Starting STORM Pipeline for {company_name}")

    # 1. Update Job Status
    jobs_dict[job_id]["status"] = JOB_STATUS.PROCESSING.value
    jobs_dict[job_id]["progress"] = 10

    try:
        # 2. Get Company ID (DB Access)
        # Background task requires its own DB session cycle
        db_engine = AsyncDatabaseEngine()
        company_id = None

        async with db_engine.get_session() as session:
            company_repo = CompanyRepository(session)
            company = await company_repo.get_by_name(company_name)
            if not company:
                raise ValueError(f"Company '{company_name}' not found in DB")
            company_id = company.id

        jobs_dict[job_id]["progress"] = 20

        # 3. Build Engine Components (src.engine.builder)
        # 3-1. LLM Configs
        lm_configs = build_lm_configs(model_provider)

        # 3-2. Hybrid Retrieval Model (Internal DB + External Search)
        rm = build_hybrid_rm(company_name=company_name, top_k=10)

        jobs_dict[job_id]["progress"] = 30

        # 4. Prepare Workspace (src.engine.io)
        base_output_dir = os.path.join("results", "enterprise")
        output_dir = create_run_directory(
            base_dir=base_output_dir,
            company_id=company_id,
            company_name=company_name,
            job_id=job_id,
        )

        # 5. Configure Runner
        engine_args = STORMWikiRunnerArguments(
            output_dir=output_dir,
            max_conv_turn=3,
            max_perspective=3,
            search_top_k=10,
            max_thread_num=3,
        )

        runner = STORMWikiRunner(engine_args, lm_configs, rm)

        # 6. Run STORM (Blocking Operation)
        # Offload to ThreadPool to keep FastAPI event loop responsive
        logger.info(f"[{job_id}] Running STORM engine in background thread...")
        full_topic = f"{company_name} {topic}"

        loop = asyncio.get_running_loop()

        def _blocking_run():
            # Metadata recording before run
            write_run_metadata(
                output_dir,
                {
                    "job_id": job_id,
                    "company": company_name,
                    "topic": topic,
                    "provider": model_provider,
                    "timestamp": str(datetime.now()),
                },
            )

            # Actual Execution
            runner.run(
                topic=full_topic,
                do_research=True,
                do_generate_outline=True,
                do_generate_article=True,
                do_polish_article=True,
            )
            runner.post_run()
            runner.summary()

        await loop.run_in_executor(None, _blocking_run)

        jobs_dict[job_id]["progress"] = 80
        logger.info(f"[{job_id}] STORM engine finished.")

        # 7. Save Results (src.engine.adapter)
        logger.info(f"[{job_id}] Saving results to DB...")

        meta_info = {
            "job_id": job_id,
            "output_dir": output_dir,
            "provider": model_provider,
        }

        report_id = await save_storm_result_to_db(
            company_name=company_name,
            topic=topic,
            output_dir=output_dir,
            model_name=model_provider,
            meta_info=meta_info,
        )

        if not report_id:
            raise RuntimeError(
                "Failed to save report to database (Adapter returned None)"
            )

        # 8. Complete
        jobs_dict[job_id]["status"] = JOB_STATUS.COMPLETED.value
        jobs_dict[job_id]["report_id"] = report_id
        jobs_dict[job_id]["progress"] = 100
        jobs_dict[job_id]["message"] = "리포트 생성이 완료되었습니다."

        logger.info(f"[{job_id}] ✅ Pipeline Success. Report ID: {report_id}")

        # Resource Cleanup
        if hasattr(rm, "close"):
            rm.close()

    except Exception as e:
        logger.error(f"[{job_id}] ❌ Pipeline Failed: {e}")
        traceback.print_exc()

        jobs_dict[job_id]["status"] = JOB_STATUS.FAILED.value
        jobs_dict[job_id]["message"] = str(e)
        jobs_dict[job_id]["progress"] = 0
