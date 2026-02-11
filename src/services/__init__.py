"""
Services Package (Lazy Loading)

무거운 의존성(torch, sentence_transformers, knowledge_storm 등)을 가진
서비스 모듈이 있으므로, 실제 사용 시점까지 import를 지연합니다.
이를 통해 백엔드 서버 시작 시간이 크게 단축됩니다.
"""
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 타입 체크 시에만 직접 import (IDE 자동완성 지원)
    from .analysis_service import AnalysisService
    from .company_service import CompanyService
    from .dart_service import DartService
    from .generated_report_service import GeneratedReportService
    from .ingestion_service import IngestionService
    from .llm_query_analyzer import LLMQueryAnalyzer
    from .report_job_service import ReportJobService
    from .reranker_service import RerankerService
    from .source_material_service import SourceMaterialService

__all__ = [
    "AnalysisService",
    "CompanyService",
    "GeneratedReportService",
    "ReportJobService",
    "SourceMaterialService",
    "LLMQueryAnalyzer",
    "RerankerService",
    "DartService",
    "IngestionService",
]

# 서비스명 → 모듈 파일 매핑
_SERVICE_MODULE_MAP: dict[str, str] = {
    "AnalysisService": ".analysis_service",
    "CompanyService": ".company_service",
    "DartService": ".dart_service",
    "GeneratedReportService": ".generated_report_service",
    "IngestionService": ".ingestion_service",
    "LLMQueryAnalyzer": ".llm_query_analyzer",
    "ReportJobService": ".report_job_service",
    "RerankerService": ".reranker_service",
    "SourceMaterialService": ".source_material_service",
}


def __getattr__(name: str):
    if name in _SERVICE_MODULE_MAP:
        module = importlib.import_module(_SERVICE_MODULE_MAP[name], __package__)
        cls = getattr(module, name)
        # 캐싱: 다음 접근 시 __getattr__ 호출 없이 바로 반환
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
