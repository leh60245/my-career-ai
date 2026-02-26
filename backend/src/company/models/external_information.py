"""
외부 검색 정보 영구 적재 모델

역할:
    - 파이프라인 실행 시 수집된 외부 검색 결과(URL, 제목, 스니펫)를 영구 저장합니다.
    - StormInformationTable 구조를 참조하여 URL 기반 중복 제거(Upsert)를 지원합니다.
    - 수집 시점(collected_at)을 기록하여 데이터 신선도(freshness) 추적이 가능합니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.src.common.models.base import Base, CreatedAtMixin


class ExternalInformation(Base, CreatedAtMixin):
    """외부 검색 정보 영구 적재 테이블"""

    __tablename__ = "external_informations"
    __table_args__ = (UniqueConstraint("url_hash", name="uq_external_informations_url_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, index=True, comment="검색 결과 원본 URL")
    url_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="URL의 SHA-256 해시 (중복 방지용 고유 키)"
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="페이지 제목")
    snippets: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="검색 스니펫 목록 (JSON 배열)")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="페이지 설명")
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="WEB", comment="출처 유형 (WEB, DART, INTERNAL)"
    )
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, comment="관련 기업명")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True, comment="수집 시점의 Job UUID")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="데이터 수집 시점"
    )
