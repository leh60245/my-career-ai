import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# =============================================================================
# 1. Environment Loading (최상위 .env 자동 탐색)
# =============================================================================
def get_project_root() -> Path:
    """
    현재 파일의 위치를 기준으로 .env 파일이 있는 프로젝트 루트를 찾습니다.
    확실한 탐색을 위해 상위로 이동하며 .env나 .git을 찾습니다.
    """
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / ".env").exists() or (parent / ".git").exists():
            return parent
    return current_path.parents[3]  # Fallback


PROJECT_ROOT = get_project_root()
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()  # 시스템 환경변수 사용


# =============================================================================
# 2. Helper Functions
# =============================================================================
def get_env(key: str, default: Any = None, cast_to: type = str) -> Any:
    """환경변수를 가져오고 원하는 타입으로 안전하게 변환합니다."""
    value = os.getenv(key)
    if value is None:
        return default

    if cast_to is bool:
        return value.lower() in ("true", "1", "yes", "on")
    if cast_to is list:
        return [x.strip() for x in value.split(",") if x.strip()]
    try:
        return cast_to(value)
    except (ValueError, TypeError):
        return default


# =============================================================================
# 3. Database Configuration
# =============================================================================
DB_CONFIG = {
    "host": get_env("PG_HOST", get_env("DB_HOST", "localhost")),
    "port": get_env("PG_PORT", get_env("DB_PORT", "5432")),
    "user": get_env("PG_USER", get_env("DB_USER", "postgres")),
    "password": get_env("PG_PASSWORD", get_env("DB_PASSWORD", "")),
    "database": get_env("PG_DATABASE", get_env("DB_NAME", "postgres")),
}

# =============================================================================
# 4. Embedding Configuration
# =============================================================================
ACTIVE_EMBEDDING_PROVIDER = get_env("EMBEDDING_PROVIDER", "huggingface")
ALLOWED_PROVIDERS = ["huggingface", "openai"]

if ACTIVE_EMBEDDING_PROVIDER not in ALLOWED_PROVIDERS:
    raise RuntimeError(f"Invalid EMBEDDING_PROVIDER: {ACTIVE_EMBEDDING_PROVIDER}. Allowed: {ALLOWED_PROVIDERS}")

_base_embedding_config = {
    "provider": ACTIVE_EMBEDDING_PROVIDER,
    "batch_size": get_env("EMBEDDING_BATCH_SIZE", 32, int),
    "max_length": get_env("EMBEDDING_MAX_LENGTH", 512, int),
    "hf_model": get_env("HF_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"),
    "hf_dimension": 768,
    "openai_model": get_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "openai_dimension": 1536,
}

# 활성 모델 동적 할당
if ACTIVE_EMBEDDING_PROVIDER == "openai":
    _base_embedding_config["dimension"] = _base_embedding_config["openai_dimension"]
    _base_embedding_config["model_name"] = _base_embedding_config["openai_model"]
else:
    _base_embedding_config["dimension"] = _base_embedding_config["hf_dimension"]
    _base_embedding_config["model_name"] = _base_embedding_config["hf_model"]

EMBEDDING_CONFIG = _base_embedding_config


def validate_embedding_dimension_compatibility():
    """임베딩 차원 호환성 검증 (하위 호환성 유지용)"""
    return True


# =============================================================================
# 5. AI & Search Configuration
# =============================================================================
AI_CONFIG = {
    "llm_provider": get_env("LLM_PROVIDER", "openai"),
    # API Keys & Endpoints
    "openai_api_key": get_env("OPENAI_API_KEY"),
    "google_api_key": get_env("GOOGLE_API_KEY"),
    "azure_api_key": get_env("AZURE_API_KEY"),
    "azure_api_base": get_env("AZURE_API_BASE"),
    "azure_api_version": get_env("AZURE_API_VERSION"),
    "serper_api_key": get_env("SERPER_API_KEY"),
    # Model & Retrieval
    "default_model": get_env("DEFAULT_LLM_MODEL", "gpt-4o"),
    "retrieval_top_k": get_env("RETRIEVAL_TOP_K", 5, int),
    "retrieval_min_score": get_env("RETRIEVAL_MIN_SCORE", 0.5, float),
    "encoder_api_type": get_env("ENCODER_API_TYPE", "openai"),
    # Reranker
    "reranker_model": "BAAI/bge-reranker-v2-m3",
    "reranker_max_length": get_env("RERANKER_MAX_LENGTH", 1024, int),
    "reranker_batch_size": get_env("RERANKER_BATCH_SIZE", 8, int),
    "reranker_device": get_env("RERANKER_DEVICE", ""),
    # Storm Logic
    "storm_max_thread_num": get_env("STORM_MAX_THREAD_NUM", 2, int),
    "storm_force_exit": get_env("STORM_FORCE_EXIT", False, bool),
}

SERPER_CONFIG = {
    "gl": get_env("SERPER_GL", "kr"),
    "hl": get_env("SERPER_HL", "ko"),
    "location": get_env("SERPER_LOCATION", "South Korea"),
    "tbs": get_env("SERPER_TBS", "qdr:y"),
    "autocorrect": get_env("SERPER_AUTOCORRECT", True, bool),
    "page": get_env("SERPER_PAGE", 1, int),
}

# =============================================================================
# 6. DART & Ingestion Configuration
# =============================================================================
DART_CONFIG = {
    "api_key": get_env("DART_API_KEY"),
    "search_start_date": get_env("DART_SEARCH_START_DATE", "20240101"),
    "report_type_code": "a001",
    "page_count": 100,
    "page_delay_sec": 0.5,
    "max_search_days": 90,
}

BATCH_CONFIG = {
    "batch_size": get_env("BATCH_SIZE", 50, int),
    "batch_delay_sec": get_env("BATCH_DELAY_SEC", 3, int),
    "request_delay_sec": get_env("REQUEST_DELAY_SEC", 0.1, float),
    "max_retries": get_env("MAX_RETRIES", 3, int),
    "retry_delay_sec": get_env("RETRY_DELAY_SEC", 5, int),
}

CHUNK_CONFIG = {
    "max_chunk_size": get_env("MAX_CHUNK_SIZE", 2000, int),
    "overlap": get_env("CHUNK_OVERLAP", 200, int),
    "min_chunk_size": get_env("MIN_CHUNK_SIZE", 100, int),
}

TARGET_SECTIONS = ["회사의 개요", "사업의 내용", "재무에 관한 사항"]

# =============================================================================
# 7. Domain Filtering
# =============================================================================
_DEFAULT_BLACKLIST = [
    "tistory.com",
    "velog.io",
    "blog.naver.com",
    "brunch.co.kr",
    "medium.com",
    "steemit.com",
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
    "quora.com",
    "reddit.com",
    "yahoo.com/answers",
    "nate.com/pann",
]

DOMAIN_BLACKLIST = _DEFAULT_BLACKLIST + get_env("EXTRA_DOMAIN_BLACKLIST", [], list)


def is_blacklisted_url(url: str) -> bool:
    if not url:
        return False
    return any(domain in url.lower() for domain in DOMAIN_BLACKLIST)


# =============================================================================
# 8. Analysis Topics
# =============================================================================
TOPICS = [
    {"id": "T01", "label": "기업 개요 및 주요 사업 내용", "value": "기업 개요 및 주요 사업 내용"},
    {"id": "T02", "label": "최근 3개년 재무제표 및 재무 상태 분석", "value": "최근 3개년 재무제표 및 재무 상태 분석"},
    {"id": "T03", "label": "산업 내 경쟁 우위 및 경쟁사 비교 (SWOT)", "value": "산업 내 경쟁 우위 및 경쟁사 비교"},
    {"id": "T04", "label": "주요 제품 및 서비스 시장 점유율 분석", "value": "주요 제품 및 서비스 시장 점유율 분석"},
    {"id": "T05", "label": "R&D 투자 현황 및 기술 경쟁력", "value": "R&D 투자 현황 및 기술 경쟁력"},
    {"id": "T06", "label": "ESG (환경, 사회, 지배구조) 평가", "value": "ESG (환경, 사회, 지배구조) 평가"},
    {"id": "custom", "label": "직접 입력", "value": None},
]
