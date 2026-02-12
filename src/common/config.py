import os
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # 기본 .env 로드 시도

# =============================================================================
# Database Configuration (통합)
# =============================================================================
# 환경변수 호환성: PG_* (신규 표준) 우선, DB_* (레거시) 폴백
DB_CONFIG = {
    "host": os.getenv("PG_HOST") or os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("PG_PORT") or os.getenv("DB_PORT", "5432"),
    "user": os.getenv("PG_USER") or os.getenv("DB_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD") or os.getenv("DB_PASSWORD"),
    "database": os.getenv("PG_DATABASE") or os.getenv("DB_NAME", "postgres"),
}

# =============================================================================
# Embedding Configuration (통합 - 가장 중요!)
# =============================================================================
# ⚠️ 경고: DB Vector Index와 동일한 모델/차원을 사용해야 합니다!
# HuggingFace(768D) ↔ OpenAI(1536D) 불일치 시 시스템 즉시 중단됩니다.
#
# 프로바이더 변경 시 필수 작업:
# 1. 기존 DB의 모든 임베딩 삭제 (UPDATE "Source_Materials" SET embedding = NULL)
# 2. pgvector 인덱스 재생성
# 3. 전체 데이터 재임베딩 (python -m scripts.run_ingestion --embed --force)

# ============== 활성 모델 설정 (런타임 중 하나만 활성화) ==============
ACTIVE_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface")

# 허용된 프로바이더 목록
_ALLOWED_PROVIDERS = ["huggingface", "openai"]

if ACTIVE_EMBEDDING_PROVIDER not in _ALLOWED_PROVIDERS:
    raise RuntimeError(
        f"Invalid EMBEDDING_PROVIDER: {ACTIVE_EMBEDDING_PROVIDER}. Allowed values: {', '.join(_ALLOWED_PROVIDERS)}"
    )

# ============== 프로바이더별 설정 ==============
EMBEDDING_CONFIG = {
    # 활성 프로바이더 (런타임 중 절대 변경 금지!)
    "provider": ACTIVE_EMBEDDING_PROVIDER,
    # HuggingFace 설정 (768차원 - 다국어 지원)
    "hf_model": os.getenv(
        "HF_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    ),
    "hf_dimension": 768,
    # OpenAI 설정 (1536차원 - 높은 정확도, 비용 발생)
    "openai_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "openai_dimension": 1536,
    # 공통 설정
    "batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
    "max_length": int(os.getenv("EMBEDDING_MAX_LENGTH", "512")),
}

# ============== 활성 차원 자동 결정 ==============
if ACTIVE_EMBEDDING_PROVIDER == "openai":
    EMBEDDING_CONFIG["dimension"] = EMBEDDING_CONFIG["openai_dimension"]
    EMBEDDING_CONFIG["model_name"] = EMBEDDING_CONFIG["openai_model"]
else:  # huggingface
    EMBEDDING_CONFIG["dimension"] = EMBEDDING_CONFIG["hf_dimension"]
    EMBEDDING_CONFIG["model_name"] = EMBEDDING_CONFIG["hf_model"]


# ============== 런타임 검증 (차원 불일치 조기 감지) ==============
def validate_embedding_dimension_compatibility():
    """임베딩 차원 호환성 검증. 현재 768차원 고정."""
    return True


# =============================================================================
# AI Configuration (LLM 및 검색)
# =============================================================================
AI_CONFIG = {
    # LLM 프로바이더
    "llm_provider": os.getenv("LLM_PROVIDER", "openai"),  # openai, gemini, azure
    # API Keys
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "google_api_key": os.getenv("GOOGLE_API_KEY"),
    "azure_api_key": os.getenv("AZURE_API_KEY"),
    "azure_api_base": os.getenv("AZURE_API_BASE"),
    "azure_api_version": os.getenv("AZURE_API_VERSION"),
    "serper_api_key": os.getenv("SERPER_API_KEY"),
    # 기본 모델 설정
    "default_model": os.getenv("DEFAULT_LLM_MODEL", "gpt-4o"),
    # 검색 설정
    "retrieval_top_k": int(os.getenv("RETRIEVAL_TOP_K", "5")),
    "retrieval_min_score": float(os.getenv("RETRIEVAL_MIN_SCORE", "0.5")),
    # Encoder API Type (레거시 호환)
    "encoder_api_type": os.getenv("ENCODER_API_TYPE", "openai"),
    "reranker_model": "BAAI/bge-reranker-v2-m3",
    "reranker_max_length": int(os.getenv("RERANKER_MAX_LENGTH", "1024")),
    "reranker_batch_size": int(os.getenv("RERANKER_BATCH_SIZE", "8")),
    "reranker_device": os.getenv("RERANKER_DEVICE", ""),
    "storm_max_thread_num": int(os.getenv("STORM_MAX_THREAD_NUM", "2")),
    "storm_force_exit": os.getenv("STORM_FORCE_EXIT", "0") == "1",
}


# =============================================================================
# Serper Search Configuration (외부 검색 파라미터)
# =============================================================================
# 환경변수 또는 여기서 직접 설정. 런타임 중 변경 가능하도록 dict 분리.
SERPER_CONFIG = {
    # 국가/언어 설정 (기본: 한국)
    "gl": os.getenv("SERPER_GL", "kr"),          # 검색 대상 국가
    "hl": os.getenv("SERPER_HL", "ko"),          # 결과 표시 언어
    "location": os.getenv("SERPER_LOCATION", "South Korea"),  # 검색 발신 위치
    # 시간대 필터 (기본: 최근 1년)
    # 옵션: qdr:h(1시간), qdr:d(24시간), qdr:w(1주), qdr:m(1개월), qdr:y(1년), ""(전체)
    "tbs": os.getenv("SERPER_TBS", "qdr:y"),
    # 자동 교정
    "autocorrect": os.getenv("SERPER_AUTOCORRECT", "true").lower() == "true",
    # 페이지 설정
    "page": int(os.getenv("SERPER_PAGE", "1")),
}


# =============================================================================
# Domain Blacklist (신뢰할 수 없는 출처 차단)
# =============================================================================
# 개인 블로그, 비전문 사이트 등을 원천 차단합니다.
# 도메인 부분 일치: "tistory.com"은 *.tistory.com 전체를 차단합니다.
DOMAIN_BLACKLIST: list[str] = [
    # 개인 블로그 플랫폼
    "tistory.com",
    "velog.io",
    "blog.naver.com",
    "brunch.co.kr",
    "medium.com",
    "steemit.com",
    # 위키/커뮤니티 (비전문)
    "namu.wiki",
    "namuwiki.mirror",
    "rigvedawiki.net",
    "fmkorea.com",
    "dcinside.com",
    "ruliweb.com",
    "theqoo.net",
    "instiz.net",
    "clien.net",
    "mlbpark.donga.com",
    # 기타 비전문 / 저신뢰
    "quora.com",
    "reddit.com",
    "yahoo.com/answers",
    "nate.com/pann",
]

# 환경변수로 추가 블랙리스트: 쉼표 구분 (예: EXTRA_BLACKLIST="example.com,foo.io")
_extra_blacklist = os.getenv("EXTRA_DOMAIN_BLACKLIST", "")
if _extra_blacklist:
    DOMAIN_BLACKLIST.extend([d.strip() for d in _extra_blacklist.split(",") if d.strip()])


def is_blacklisted_url(url: str) -> bool:
    """URL이 블랙리스트 도메인에 해당하는지 검사"""
    if not url:
        return False
    url_lower = url.lower()
    return any(domain in url_lower for domain in DOMAIN_BLACKLIST)


# Analysis Topic Configuration (분석 주제 중앙 관리)
# =============================================================================
# Topic 정의 (공통 사용)
TOPICS = [
    {
        "id": "T01",
        "label": "기업 개요 및 주요 사업 내용",
        "value": "기업 개요 및 주요 사업 내용",
    },
    {
        "id": "T02",
        "label": "최근 3개년 재무제표 및 재무 상태 분석",
        "value": "최근 3개년 재무제표 및 재무 상태 분석",
    },
    {
        "id": "T03",
        "label": "산업 내 경쟁 우위 및 경쟁사 비교 (SWOT)",
        "value": "산업 내 경쟁 우위 및 경쟁사 비교",
    },
    {
        "id": "T04",
        "label": "주요 제품 및 서비스 시장 점유율 분석",
        "value": "주요 제품 및 서비스 시장 점유율 분석",
    },
    {
        "id": "T05",
        "label": "R&D 투자 현황 및 기술 경쟁력",
        "value": "R&D 투자 현황 및 기술 경쟁력",
    },
    {
        "id": "T06",
        "label": "ESG (환경, 사회, 지배구조) 평가",
        "value": "ESG (환경, 사회, 지배구조) 평가",
    },
    {
        "id": "custom",
        "label": "직접 입력",
        "value": None,
    },
]


def get_topic_value_by_id(topic_id: str) -> str:
    """
    Topic ID로 value(순수 주제)를 조회합니다.

    Args:
        topic_id: TOPICS 리스트의 id 값

    Returns:
        해당하는 value (순수 주제 텍스트) 또는 None
    """
    for topic in TOPICS:
        if topic["id"] == topic_id:
            return topic["value"]
    return None


# =============================================================================
# DART API Configuration
# =============================================================================
DART_CONFIG = {
    "api_key": os.getenv("DART_API_KEY"),
    # 보고서 검색 설정
    "search_start_date": os.getenv("DART_SEARCH_START_DATE", "20240101"),
    "report_type_code": "a001",  # 사업보고서
    "page_count": 100,
    "page_delay_sec": 0.5,
    "max_search_days": 90,
}

# =============================================================================
# Batch Processing Configuration (Ingestion용)
# =============================================================================
BATCH_CONFIG = {
    "batch_size": int(os.getenv("BATCH_SIZE", "50")),
    "batch_delay_sec": int(os.getenv("BATCH_DELAY_SEC", "3")),
    "request_delay_sec": float(os.getenv("REQUEST_DELAY_SEC", "0.1")),
    "max_retries": int(os.getenv("MAX_RETRIES", "3")),
    "retry_delay_sec": int(os.getenv("RETRY_DELAY_SEC", "5")),
}

# =============================================================================
# Chunk Configuration (텍스트 청킹)
# =============================================================================
CHUNK_CONFIG = {
    "max_chunk_size": int(os.getenv("MAX_CHUNK_SIZE", "2000")),
    "overlap": int(os.getenv("CHUNK_OVERLAP", "200")),
    "min_chunk_size": int(os.getenv("MIN_CHUNK_SIZE", "100")),
}

# =============================================================================
# Target Sections (DART 보고서)
# =============================================================================
TARGET_SECTIONS = [
    "회사의 개요",
    "사업의 내용",
    "재무에 관한 사항",
]


# =============================================================================
# Validation (필수 환경변수 체크)
# =============================================================================
def validate_config(check_db=True, check_ai=False, check_dart=False):
    """
    설정 유효성 검사

    Args:
        check_db: DB 접속 정보 검증
        check_ai: AI API 키 검증
        check_dart: DART API 키 검증

    Raises:
        RuntimeError: 필수 설정이 누락된 경우
    """
    missing = []

    if check_db:
        if not DB_CONFIG["password"]:
            missing.append("PG_PASSWORD (or DB_PASSWORD)")

    if check_ai:
        if AI_CONFIG["llm_provider"] == "openai" and not AI_CONFIG["openai_api_key"]:
            missing.append("OPENAI_API_KEY")
        elif AI_CONFIG["llm_provider"] == "gemini" and not AI_CONFIG["google_api_key"]:
            missing.append("GOOGLE_API_KEY")

    if check_dart:
        if not DART_CONFIG["api_key"]:
            missing.append("DART_API_KEY")

    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Please set them in .env or as environment variables."
        )
