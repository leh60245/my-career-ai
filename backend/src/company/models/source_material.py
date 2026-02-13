from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.common.models.base import Base, CreatedAtMixin


if TYPE_CHECKING:
    from .analysis_report import AnalysisReport


class SourceMaterial(Base, CreatedAtMixin):
    __tablename__ = "source_materials"

    # Fields
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_report_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_reports.id"), nullable=False)

    chunk_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    table_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 벡터 차원은 EMBEDDING_CONFIG['dimension']과 반드시 일치해야 합니다.
    # 프로바이더 변경(HuggingFace 768D ↔ OpenAI 1536D) 시 함께 수정 필요
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    meta_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    analysis_report: Mapped["AnalysisReport"] = relationship("AnalysisReport", back_populates="source_materials")
