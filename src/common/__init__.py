"""
공통 모듈 (Common Module)

AI와 Ingestion 양쪽에서 공유하는 핵심 컴포넌트:
- config: 전역 설정 (API 키, DB 접속 정보, 모델 설정)
- db_connection: 통합 DB 연결 관리
- embedding: 통합 임베딩 서비스 (OpenAI/HuggingFace)
- utils: 공통 유틸리티 함수
"""

import importlib
from typing import TYPE_CHECKING

# 가벼운 config 값들은 즉시 import (모두 dict/list/str 등 단순 값)
from .config import (
    AI_CONFIG,
    BATCH_CONFIG,
    CHUNK_CONFIG,
    DART_CONFIG,
    DB_CONFIG,
    EMBEDDING_CONFIG,
    TARGET_SECTIONS,
    TOPICS,
)

# Enums도 가벼우므로 즉시 import
from .enums import AnalysisReportStatus, ReportJobStatus

if TYPE_CHECKING:
    # IDE 자동완성을 위한 타입 힌트용 import
    from .embedding import Embedding
    from .entity_resolver import CompanyEntityResolver

__all__ = [
    "TOPICS",
    "DB_CONFIG",
    "EMBEDDING_CONFIG",
    "DART_CONFIG",
    "BATCH_CONFIG",
    "AI_CONFIG",
    "CHUNK_CONFIG",
    "TARGET_SECTIONS",
    "Embedding",
    "CompanyEntityResolver",
    "ReportJobStatus",
    "AnalysisReportStatus",
]

# 무거운 클래스(Embedding, CompanyEntityResolver)는 실제 사용 시 지연 로딩
_LAZY_MODULE_MAP: dict[str, str] = {
    "Embedding": ".embedding",
    "CompanyEntityResolver": ".entity_resolver",
}


def __getattr__(name: str):
    if name in _LAZY_MODULE_MAP:
        module = importlib.import_module(_LAZY_MODULE_MAP[name], __package__)
        cls = getattr(module, name)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
