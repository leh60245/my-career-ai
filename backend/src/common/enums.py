from enum import StrEnum


# ============================================================
# User & Affiliation Domain
# ============================================================

class UserRole(StrEnum):
    """사용자 역할"""
    JOB_SEEKER = "JOB_SEEKER"      # 구직자
    MANAGER = "MANAGER"            # 관리자 (대학, 공공기관 등)
    SYSTEM_ADMIN = "SYSTEM_ADMIN"  # 시스템 관리자


class UserTier(StrEnum):
    """구독 등급"""
    FREE = "FREE"
    PRO = "PRO"


class AffiliationType(StrEnum):
    """소속 기관 유형"""
    UNIVERSITY = "UNIVERSITY"    # 대학교
    GOVERNMENT = "GOVERNMENT"    # 공공기관
    COMPANY = "COMPANY"          # 기업
    ETC = "ETC"                  # 기타


# ============================================================
# Company Domain
# ============================================================

class AnalysisReportStatus(StrEnum):
    PENDING = "PENDING"  # 데이터 생성 됨, 처리 대기
    PROCESSING = "PROCESSING"  # 임베딩/청킹 작업 중
    COMPLETED = "COMPLETED"  # 작업 완료 (검색 가능)
    FAILED = "FAILED"  # 처리 중 에러 발생


class ReportJobStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ============================================================
# Resume Domain
# ============================================================

class ResumeItemType(StrEnum):
    """자소서 문항 유형"""
    MOTIVATION = "MOTIVATION"          # 지원동기
    COMPETENCY = "COMPETENCY"          # 직무역량
    CHALLENGE = "CHALLENGE"            # 도전
    COLLABORATION = "COLLABORATION"    # 협력
    VALUES = "VALUES"                  # 가치관
    SOCIAL_ISSUE = "SOCIAL_ISSUE"      # 사회이슈
