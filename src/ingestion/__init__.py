"""
데이터 수집 패키지 (Ingestion Package)

DART API를 통한 사업보고서 수집 및 DB 적재를 담당합니다.
이 패키지는 데이터를 "집어넣는(Write)" 역할에 집중합니다.

구성:
- dart_agent: DART API 연동 및 보고서 파싱
- pipeline: 데이터 수집 오케스트레이션
- embedding_worker: 임베딩 생성 워커
"""

from .dart_agent import DartReportAgent
from .embedding_worker import ContextLookbackEmbeddingWorker
from .pipeline import DataPipeline

__all__ = [
    "DartReportAgent",
    "DataPipeline",
    "ContextLookbackEmbeddingWorker",
]
