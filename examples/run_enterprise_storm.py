"""
Enterprise STORM Pipeline - 기업 분석 리포트 일괄 생성

PostgreSQL 내부 DB를 활용한 기업 분석 리포트 생성 파이프라인입니다.
외부 검색 엔진 대신 PostgresRM을 사용하여 DART 보고서 데이터를 기반으로 분석합니다.

Required Environment Variables (secrets.toml):
    - OPENAI_API_KEY: OpenAI API key
    - OPENAI_API_TYPE: 'openai' (기본값)
    - PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE: PostgreSQL 접속 정보

Output Structure:
    output_dir/
        topic_name/
            conversation_log.json
            raw_search_results.json
            direct_gen_outline.txt
            storm_gen_outline.txt
            url_to_info.json
            storm_gen_article.txt
            storm_gen_article_polished.txt

Author: Enterprise STORM Team
Date: 2026-01-08
"""

import os
import sys
import re
import logging
from datetime import datetime
from argparse import ArgumentParser

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm import (
    STORMWikiRunnerArguments,
    STORMWikiRunner,
    STORMWikiLMConfigs,
)
from knowledge_storm.lm import OpenAIModel, AzureOpenAIModel
from knowledge_storm.rm import PostgresRM
from knowledge_storm.utils import load_api_key

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# 분석 타겟 리스트 (Batch Processing Targets)
# ============================================================
ANALYSIS_TARGETS = [
    "삼성전자 기업 개요 및 주요 사업의 내용"
    # "삼성전자 최근 3개년 요약 재무제표 및 재무 상태 분석",
    # "삼성전자 SWOT 분석 (강점, 약점, 기회, 위협)",
    # "삼성전자 3C 분석 (자사, 경쟁사, 고객)",
    # "삼성전자 채용 공고 및 인재상 분석"
]


def create_topic_dir_name(topic: str) -> str:
    """
    토픽명을 파일시스템 호환 디렉토리명으로 변환

    Args:
        topic: 원본 토픽명

    Returns:
        언더스코어로 연결된 디렉토리명
    """
    # 공백, 슬래시, 괄호 등을 언더스코어로 변환
    dir_name = re.sub(r'[\s/\\()（）,，]', '_', topic)
    dir_name = re.sub(r'_+', '_', dir_name)  # 연속된 언더스코어 제거
    dir_name = dir_name.strip('_')
    return dir_name


def setup_lm_configs() -> STORMWikiLMConfigs:
    """
    LLM 설정을 초기화합니다.

    Returns:
        STORMWikiLMConfigs: 설정된 LM 구성 객체
    """
    lm_configs = STORMWikiLMConfigs()

    openai_kwargs = {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "temperature": 1.0,
        "top_p": 0.9,
    }

    # API 타입에 따른 모델 클래스 선택
    api_type = os.getenv("OPENAI_API_TYPE", "openai")
    ModelClass = OpenAIModel if api_type == "openai" else AzureOpenAIModel

    # 모델명 설정
    gpt_35_model_name = "gpt-3.5-turbo" if api_type == "openai" else "gpt-35-turbo"
    gpt_4_model_name = "gpt-4o"

    # Azure 설정 (필요시)
    if api_type == "azure":
        openai_kwargs["api_base"] = os.getenv("AZURE_API_BASE")
        openai_kwargs["api_version"] = os.getenv("AZURE_API_VERSION")

    # 각 컴포넌트별 LM 설정
    # - conv_simulator_lm, question_asker_lm: 저렴한 모델 (대화 시뮬레이션)
    # - outline_gen_lm, article_gen_lm, article_polish_lm: 강력한 모델 (콘텐츠 생성)
    conv_simulator_lm = ModelClass(
        model=gpt_35_model_name, max_tokens=500, **openai_kwargs
    )
    question_asker_lm = ModelClass(
        model=gpt_35_model_name, max_tokens=500, **openai_kwargs
    )
    outline_gen_lm = ModelClass(
        model=gpt_4_model_name, max_tokens=400, **openai_kwargs
    )
    article_gen_lm = ModelClass(
        model=gpt_4_model_name, max_tokens=700, **openai_kwargs
    )
    article_polish_lm = ModelClass(
        model=gpt_4_model_name, max_tokens=4000, **openai_kwargs
    )

    lm_configs.set_conv_simulator_lm(conv_simulator_lm)
    lm_configs.set_question_asker_lm(question_asker_lm)
    lm_configs.set_outline_gen_lm(outline_gen_lm)
    lm_configs.set_article_gen_lm(article_gen_lm)
    lm_configs.set_article_polish_lm(article_polish_lm)

    return lm_configs


def run_batch_analysis(args):
    """
    배치 분석을 실행합니다.

    Args:
        args: ArgumentParser에서 파싱된 인자
    """
    # secrets.toml 로드
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
    if os.path.exists(secrets_path):
        load_api_key(toml_file_path=secrets_path)
        logger.info(f"✓ Loaded secrets from: {secrets_path}")
    else:
        # 현재 디렉토리에서도 찾기
        if os.path.exists("secrets.toml"):
            load_api_key(toml_file_path="secrets.toml")
            logger.info("✓ Loaded secrets from: secrets.toml")
        else:
            logger.error("✗ secrets.toml not found!")
            logger.error("  Please create secrets.toml with required API keys and DB credentials.")
            sys.exit(1)

    # LM 설정 초기화
    logger.info("Initializing LM configurations...")
    lm_configs = setup_lm_configs()

    # PostgresRM 초기화 (내부 DB 검색)
    logger.info("Initializing PostgresRM (Internal DB Search)...")
    rm = PostgresRM(k=args.search_top_k, min_score=args.min_score)
    logger.info(f"✓ PostgresRM initialized with k={args.search_top_k}, min_score={args.min_score}")

    # 분석 대상 리스트 결정
    if args.topics:
        # 커맨드라인에서 지정된 토픽 사용
        analysis_targets = args.topics
    else:
        # 기본 분석 타겟 사용
        analysis_targets = ANALYSIS_TARGETS

    total_topics = len(analysis_targets)
    successful = 0
    failed = 0

    logger.info("=" * 60)
    logger.info(f"Starting Enterprise STORM Batch Analysis")
    logger.info(f"Total topics to process: {total_topics}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info("=" * 60)

    for idx, topic in enumerate(analysis_targets, 1):
        topic_start_time = datetime.now()
        logger.info("")
        logger.info(f"[{idx}/{total_topics}] Processing: '{topic}'")
        logger.info("-" * 50)

        try:
            # 각 토픽별로 별도의 출력 디렉토리 설정
            # 토픽명을 디렉토리명으로 변환하여 결과가 덮어씌워지지 않도록 함
            topic_dir_name = create_topic_dir_name(topic)
            topic_output_dir = os.path.join(args.output_dir, topic_dir_name)

            # Engine Arguments 설정
            engine_args = STORMWikiRunnerArguments(
                output_dir=args.output_dir,  # 기본 출력 디렉토리
                max_conv_turn=args.max_conv_turn,
                max_perspective=args.max_perspective,
                search_top_k=args.search_top_k,
                max_thread_num=args.max_thread_num,
            )

            # Runner 생성
            runner = STORMWikiRunner(engine_args, lm_configs, rm)

            # STORM 파이프라인 실행
            runner.run(
                topic=topic,
                do_research=args.do_research,
                do_generate_outline=args.do_generate_outline,
                do_generate_article=args.do_generate_article,
                do_polish_article=args.do_polish_article,
            )
            runner.post_run()
            runner.summary()

            elapsed = datetime.now() - topic_start_time
            logger.info(f"✓ Completed '{topic}' in {elapsed.total_seconds():.1f}s")
            successful += 1

        except Exception as e:
            elapsed = datetime.now() - topic_start_time
            logger.error(f"✗ Failed '{topic}' after {elapsed.total_seconds():.1f}s")
            logger.error(f"  Error: {e}")
            failed += 1

            if args.stop_on_error:
                logger.error("Stopping due to --stop-on-error flag")
                break

    # PostgresRM 연결 종료
    rm.close()

    # 최종 요약
    logger.info("")
    logger.info("=" * 60)
    logger.info("Batch Analysis Complete!")
    logger.info(f"  Successful: {successful}/{total_topics}")
    logger.info(f"  Failed: {failed}/{total_topics}")
    logger.info(f"  Output directory: {args.output_dir}")
    logger.info("=" * 60)


def main():
    parser = ArgumentParser(
        description="Enterprise STORM - 기업 분석 리포트 일괄 생성 도구"
    )

    # 출력 설정
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./results/enterprise",
        help="결과물 저장 디렉토리 (기본값: ./results/enterprise)",
    )

    # 토픽 설정 (선택적)
    parser.add_argument(
        "--topics",
        type=str,
        nargs="+",
        default=None,
        help="분석할 토픽 리스트 (미지정시 기본 리스트 사용)",
    )

    # PostgresRM 설정
    parser.add_argument(
        "--search-top-k",
        type=int,
        default=10,
        help="검색 결과 상위 k개 (기본값: 10)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.5,
        help="최소 유사도 점수 임계값 (기본값: 0.5)",
    )

    # STORM 엔진 설정
    parser.add_argument(
        "--max-conv-turn",
        type=int,
        default=3,
        help="최대 대화 턴 수 (기본값: 3)",
    )
    parser.add_argument(
        "--max-perspective",
        type=int,
        default=3,
        help="최대 관점 수 (기본값: 3)",
    )
    parser.add_argument(
        "--max-thread-num",
        type=int,
        default=3,
        help="최대 스레드 수 (기본값: 3)",
    )

    # 파이프라인 단계 설정
    parser.add_argument(
        "--do-research",
        action="store_true",
        default=True,
        help="리서치 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-generate-outline",
        action="store_true",
        default=True,
        help="아웃라인 생성 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-generate-article",
        action="store_true",
        default=True,
        help="아티클 생성 단계 실행 (기본값: True)",
    )
    parser.add_argument(
        "--do-polish-article",
        action="store_true",
        default=True,
        help="아티클 다듬기 단계 실행 (기본값: True)",
    )

    # 에러 처리
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="에러 발생 시 배치 처리 중단",
    )

    args = parser.parse_args()

    # action="store_true"와 default=True가 함께 사용되면 항상 True가 되므로
    # 기본값이 True인 플래그들은 명시적으로 설정
    if not any([args.do_research, args.do_generate_outline,
                args.do_generate_article, args.do_polish_article]):
        args.do_research = True
        args.do_generate_outline = True
        args.do_generate_article = True
        args.do_polish_article = True

    run_batch_analysis(args)


if __name__ == "__main__":
    main()

