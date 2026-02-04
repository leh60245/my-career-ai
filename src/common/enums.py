from enum import Enum


class AnalysisReportStatus(str, Enum):
    PENDING = "PENDING"  # 데이터 생성 됨, 처리 대기
    PROCESSING = "PROCESSING"  # 임베딩/청킹 작업 중
    COMPLETED = "COMPLETED"  # 작업 완료 (검색 가능)
    FAILED = "FAILED"  # 처리 중 에러 발생


class ReportJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
