"""
STORM Engine Wrapper Service for Backend API Integration

Task ID: FEAT-Core-001-EngineIntegration
Task ID: FIX-Core-002-SaveLogic & Encoding (Post-Processing Bridge)
Purpose: FastAPI와 knowledge_storm 라이브러리를 연결하는 Wrapper Service

Architecture:
    - scripts/run_storm.py의 메인 로직을 함수 형태로 변환
    - argparse 의존성 제거 → 함수 파라미터로 입력 받음
    - BackgroundTasks와 연동하여 비동기 실행 가능
    - ✅ Post-Processing Bridge: 파일 읽기 → DB 저장

Key Fix:
    - STORMWikiRunner.run()은 파일만 생성 (DB 저장 안 함)
    - 수정: runner.run() 후 파일을 읽어 DB에 INSERT (RETURNING id)
    - 한글 인코딩: 모든 파일 읽기에 encoding='utf-8' 명시

Usage:
    from backend.storm_service import run_storm_pipeline
    
    background_tasks.add_task(
        run_storm_pipeline,
        job_id="job-123",
        company_name="삼성전자",
        topic="기업 개요",
        jobs_dict=JOBS
    )

Author: Backend Development Team
Created: 2026-01-17
Updated: 2026-01-17 (Post-Processing Bridge Implementation)
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm import (
    STORMWikiRunnerArguments,
    STORMWikiRunner,
    STORMWikiLMConfigs,
)
from knowledge_storm.lm import OpenAIModel, GoogleModel
from knowledge_storm.rm import PostgresRM
from knowledge_storm.utils import load_api_key

from src.common.config import extract_companies_from_query
from backend.database import get_db_cursor, get_db_connection
from psycopg2.extras import RealDictCursor
import psycopg2

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================
# Post-Processing Bridge Functions (FIX-Core-002)
# ============================================================
# 라이브러리(run())는 '작가'일 뿐, 원고를 서고(DB)에 꽂는 것은 '사서(Developer)'가 직접 해야 합니다.

def _find_report_file(output_dir: str) -> str | None:
    """
    임시 폴더에서 생성된 마크다운 리포트 파일을 찾습니다.
    
    패턴: storm_gen_article_polished.txt 또는 storm_gen_article.txt
    
    Args:
        output_dir: runner가 작업한 임시 폴더 (예: ./results/temp/job-xyz)
    
    Returns:
        파일 경로 (문자열) 또는 None
    
    Example:
        file_path = _find_report_file("./results/temp/job-abc123")
        # → "./results/temp/job-abc123/storm_gen_article_polished.txt"
    """
    if not os.path.exists(output_dir):
        logger.warning(f"Output directory not found: {output_dir}")
        return None
    
    # 순서대로 찾기
    candidates = [
        "storm_gen_article_polished.txt",
        "storm_gen_article.txt",
    ]
    
    for filename in candidates:
        file_path = os.path.join(output_dir, filename)
        if os.path.exists(file_path):
            logger.info(f"✓ Found report file: {filename}")
            return file_path
    
    logger.warning(f"No report file found in: {output_dir}")
    return None


def _read_report_content(file_path: str) -> str | None:
    """
    마크다운 리포트 파일을 UTF-8로 읽어 메모리에 로드합니다.
    
    ⚠️ 중요: encoding='utf-8' 명시적 선언으로 한글 인코딩 깨짐 방지
    
    Args:
        file_path: 리포트 파일 경로
    
    Returns:
        파일 내용 (문자열) 또는 None (읽기 실패 시)
    
    Example:
        content = _read_report_content("./results/temp/job-abc123/storm_gen_article_polished.txt")
        # → "# 삼성전자 기업 개요\n\n## 1. 개요\n..."
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"✓ Read report file ({len(content)} bytes)")
        return content
    except UnicodeDecodeError as e:
        logger.error(f"❌ UTF-8 Encoding error: {e}")
        logger.warning("Retrying with fallback encoding (cp949)...")
        try:
            with open(file_path, "r", encoding="cp949") as f:
                content = f.read()
            logger.warning(f"⚠️  Fallback encoding used (cp949)")
            return content
        except Exception as e2:
            logger.error(f"❌ Fallback encoding also failed: {e2}")
            return None
    except Exception as e:
        logger.error(f"❌ Failed to read report file: {e}")
        return None


def _save_report_to_db(
    company_name: str,
    topic: str,
    report_content: str,
    model_name: str = "gpt-4o"
) -> int | None:
    """
    리포트를 DB의 Generated_Reports 테이블에 저장합니다.
    
    ✅ RETURNING id 구문으로 즉시 primary key 획득
    
    Args:
        company_name: 기업명 (예: "삼성전자")
        topic: 순수 주제 (기업명 제거됨, 예: "기업 개요")
        report_content: 마크다운 리포트 내용
        model_name: 사용된 LLM 모델명 (기본값: gpt-4o)
    
    Returns:
        생성된 report_id (정수) 또는 None (저장 실패 시)
    
    Example:
        report_id = _save_report_to_db(
            company_name="삼성전자",
            topic="기업 개요",
            report_content="# 삼성전자 기업 개요\n...",
            model_name="gpt-4o"
        )
        # → 42 (생성된 ID)
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # INSERT + RETURNING id (PostgreSQL 문법)
        sql = """
            INSERT INTO "Generated_Reports" 
            (company_name, topic, report_content, model_name, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id
        """
        
        cur.execute(sql, (company_name, topic, report_content, model_name))
        result = cur.fetchone()
        report_id = result['id'] if result else None
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✓ Saved to DB - Report ID: {report_id}")
        return report_id
        
    except psycopg2.Error as e:
        logger.error(f"❌ DB Error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return None


def _load_and_save_report_bridge(
    output_dir: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,
    job_id: str,
    model_name: str = "gpt-4o"
) -> int | None:
    """
    Post-Processing Bridge: 파일 시스템 → DB
    
    이 함수는 다음을 순차적으로 수행합니다:
    1. 파일 탐색 (File Discovery)
    2. 파일 읽기 (Read to Memory) - UTF-8 명시
    3. DB INSERT (Save to DB) - RETURNING id
    4. 상태 동기화 (Update Status) - jobs_dict 업데이트
    
    Args:
        output_dir: runner가 작업한 임시 폴더 경로
        company_name: 기업명
        topic: 순수 주제
        jobs_dict: 메모리 작업 상태 딕셔너리
        job_id: 작업 ID
        model_name: LLM 모델명
    
    Returns:
        저장된 report_id (정수) 또는 None
    """
    logger.info(f"[{job_id}] Starting Post-Processing Bridge...")
    
    # ============================================================
    # Step 1: File Discovery - 리포트 파일 찾기
    # ============================================================
    report_file = _find_report_file(output_dir)
    if not report_file:
        logger.error(f"❌ Report file not found in {output_dir}")
        jobs_dict[job_id]["message"] = "리포트 파일을 찾을 수 없습니다."
        return None
    
    # ============================================================
    # Step 2: Read to Memory - UTF-8로 파일 읽기
    # ============================================================
    report_content = _read_report_content(report_file)
    if not report_content:
        logger.error(f"❌ Failed to read report content")
        jobs_dict[job_id]["message"] = "리포트 내용을 읽을 수 없습니다."
        return None
    
    # ============================================================
    # Step 3: Save to DB - INSERT with RETURNING id
    # ============================================================
    report_id = _save_report_to_db(company_name, topic, report_content, model_name)
    if report_id is None:
        logger.error(f"❌ Failed to save report to DB")
        jobs_dict[job_id]["message"] = "DB 저장 중 오류가 발생했습니다."
        return None
    
    # ============================================================
    # Step 4: Update Status - 메모리 상태 동기화
    # ============================================================
    jobs_dict[job_id]["report_id"] = report_id
    jobs_dict[job_id]["message"] = f"리포트 생성이 완료되었습니다. (Report ID: {report_id})"
    
    logger.info(f"✅ Bridge completed: report_id={report_id}")
    return report_id


    """
    LLM Configuration 설정
    
    Args:
        model_provider: "openai" 또는 "gemini"
    
    Returns:
        STORMWikiLMConfigs: 설정된 LM Config 객체
    """
    lm_configs = STORMWikiLMConfigs()

    if model_provider == "gemini":
        # Gemini 모델 설정
        gemini_kwargs = {
            "api_key": os.getenv("GOOGLE_API_KEY"),
            "temperature": 1.0,
            "top_p": 0.9,
        }

        gemini_flash_model = "gemini-2.0-flash-exp"
        gemini_pro_model = "gemini-2.0-flash"

        conv_simulator_lm = GoogleModel(
            model=gemini_flash_model, max_tokens=2048, **gemini_kwargs
        )
        question_asker_lm = GoogleModel(
            model=gemini_flash_model, max_tokens=2048, **gemini_kwargs
        )
        outline_gen_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=4096, **gemini_kwargs
        )
        article_gen_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=8192, **gemini_kwargs
        )
        article_polish_lm = GoogleModel(
            model=gemini_pro_model, max_tokens=8192, **gemini_kwargs
        )

        logger.info(f"✓ Using Gemini models: {gemini_flash_model} (fast), {gemini_pro_model} (pro)")

    else:
        # OpenAI 모델 설정 (기본값)
        openai_kwargs = {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "temperature": 1.0,
            "top_p": 0.9,
        }

        gpt_35_model_name = "gpt-4o-mini"
        gpt_4_model_name = "gpt-4o"

        conv_simulator_lm = OpenAIModel(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        question_asker_lm = OpenAIModel(
            model=gpt_35_model_name, max_tokens=500, **openai_kwargs
        )
        outline_gen_lm = OpenAIModel(
            model=gpt_4_model_name, max_tokens=400, **openai_kwargs
        )
        article_gen_lm = OpenAIModel(
            model=gpt_4_model_name, max_tokens=700, **openai_kwargs
        )
        article_polish_lm = OpenAIModel(
            model=gpt_4_model_name, max_tokens=4000, **openai_kwargs
        )

        logger.info(f"✓ Using OpenAI models: {gpt_35_model_name} (fast), {gpt_4_model_name} (pro)")

    lm_configs.set_conv_simulator_lm(conv_simulator_lm)
    lm_configs.set_question_asker_lm(question_asker_lm)
    lm_configs.set_outline_gen_lm(outline_gen_lm)
    lm_configs.set_article_gen_lm(article_gen_lm)
    lm_configs.set_article_polish_lm(article_polish_lm)

    return lm_configs


def run_storm_pipeline(
    job_id: str,
    company_name: str,
    topic: str,
    jobs_dict: dict,
    model_provider: str = "openai"
):
    """
    STORM 엔진 실행 메인 함수 (Background Task용)
    
    Args:
        job_id: 작업 추적용 고유 ID (예: "job-123")
        company_name: 기업명 (예: "삼성전자")
        topic: 순수 주제 (기업명 제거된 상태, 예: "기업 개요")
        jobs_dict: 작업 상태 저장용 In-memory Dictionary
        model_provider: LLM 프로바이더 ("openai" 또는 "gemini")
    
    Flow:
        1. Status Update → processing
        2. STORM 엔진 설정 및 실행
        3. DB에 결과 저장 (STORMWikiRunner가 자동 저장)
        4. 최신 report_id 조회
        5. Status Update → completed
    
    Exception Handling:
        - 실행 중 예외 발생 시 status를 "failed"로 변경하고 에러 메시지 저장
    """
    try:
        logger.info(f"[{job_id}] Starting STORM Pipeline")
        logger.info(f"  Company: {company_name}")
        logger.info(f"  Topic: {topic}")
        logger.info(f"  Model Provider: {model_provider}")

        # ============================================================
        # Step 1: Update Status → Processing
        # ============================================================
        jobs_dict[job_id]["status"] = "processing"
        jobs_dict[job_id]["progress"] = 10
        
        # ============================================================
        # Step 2: Load API Keys (환경변수에서 자동 로드)
        # ============================================================
        # secrets.toml이 있으면 로드 (선택사항)
        secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
        if os.path.exists(secrets_path):
            load_api_key(toml_file_path=secrets_path)
            logger.info(f"✓ Loaded secrets from: {secrets_path}")
        
        # ============================================================
        # Step 3: Topic 전처리 (중요!)
        # ============================================================
        # API에서는 이미 clean_topic을 받지만, 혹시 모를 중복 제거
        clean_topic = topic.replace(company_name, "").strip()
        clean_topic = " ".join(clean_topic.split())  # 다중 공백 정규화
        
        # LLM에는 "{company_name} {topic}" 형식으로 전달
        full_topic_for_llm = f"{company_name} {clean_topic}".strip()
        
        logger.info(f"  Clean Topic: {clean_topic}")
        logger.info(f"  Full Topic for LLM: {full_topic_for_llm}")
        
        # ============================================================
        # Step 4: LM Configurations 초기화
        # ============================================================
        jobs_dict[job_id]["progress"] = 20
        logger.info("Initializing LM configurations...")
        lm_configs = _setup_lm_configs(model_provider)
        
        # ============================================================
        # Step 5: PostgresRM 초기화 (내부 DB 검색)
        # ============================================================
        jobs_dict[job_id]["progress"] = 30
        logger.info("Initializing PostgresRM...")
        
        # MVP 최적화 설정 (속도 우선)
        search_top_k = 10
        min_score = 0.5
        
        rm = PostgresRM(k=search_top_k, min_score=min_score)
        rm.set_company_filter(company_name)
        
        logger.info(f"✓ PostgresRM initialized with k={search_top_k}, company_filter={company_name}")
        
        # ============================================================
        # Step 6: STORM Engine Arguments 설정
        # ============================================================
        jobs_dict[job_id]["progress"] = 40
        
        # 임시 저장소 (나중에 타임스탬프 기반으로 변경 가능)
        output_dir = f"./results/temp/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        engine_args = STORMWikiRunnerArguments(
            output_dir=output_dir,
            max_conv_turn=3,         # MVP 최적화 (속도)
            max_perspective=3,       # MVP 최적화
            search_top_k=search_top_k,
            max_thread_num=3,
        )
        
        logger.info(f"✓ Engine arguments configured (output_dir={output_dir})")
        
        # ============================================================
        # Step 7: STORM Runner 실행 (Long-running process!)
        # ============================================================
        jobs_dict[job_id]["progress"] = 50
        logger.info("Starting STORM Runner...")
        
        runner = STORMWikiRunner(engine_args, lm_configs, rm)
        
        # 실제 생성 실행 (1~2분 소요)
        runner.run(
            topic=full_topic_for_llm,
            do_research=True,
            do_generate_outline=True,
            do_generate_article=True,
            do_polish_article=True
        )
        
        jobs_dict[job_id]["progress"] = 80
        logger.info("✓ STORM Runner completed successfully")
        
        # Post-processing
        runner.post_run()
        runner.summary()
        
        # ============================================================
        # Step 8: Post-Processing Bridge (FIX-Core-002!)
        # ============================================================
        # ✅ 파일 읽기 → DB 저장 → Report ID 획득
        jobs_dict[job_id]["progress"] = 85
        logger.info("Starting Post-Processing Bridge...")
        
        report_id = _load_and_save_report_bridge(
            output_dir=output_dir,
            company_name=company_name,
            topic=clean_topic,
            jobs_dict=jobs_dict,
            job_id=job_id,
            model_name="gpt-4o"  # 차후 파라미터로 변경 가능
        )
        
        if report_id is None:
            raise Exception("Post-Processing Bridge failed: Report ID is None")
        
        # ============================================================
        # Step 9: Update Status → Completed
        # ============================================================
        jobs_dict[job_id]["status"] = "completed"
        jobs_dict[job_id]["report_id"] = report_id
        jobs_dict[job_id]["progress"] = 100
        jobs_dict[job_id]["message"] = f"리포트 생성이 완료되었습니다. (Report ID: {report_id})"
        
        logger.info(f"[{job_id}] ✅ Pipeline completed successfully")
        logger.info(f"  Report ID: {report_id}")
        
    except Exception as e:
        # ============================================================
        # Error Handling
        # ============================================================
        logger.error(f"[{job_id}] ❌ Pipeline failed: {e}")
        logger.exception("Full traceback:")
        
        jobs_dict[job_id]["status"] = "failed"
        jobs_dict[job_id]["message"] = f"리포트 생성 중 오류 발생: {str(e)}"
        jobs_dict[job_id]["progress"] = 0
        
        # RM이 초기화되었다면 연결 종료
        try:
            if 'rm' in locals():
                rm.close()
        except:
            pass
