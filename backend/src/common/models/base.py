from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """모든 도메인 모델의 최상위 Base 클래스."""

    __abstract__ = True
    type_annotation_map = {}

    id: Any

    def to_dict(self) -> dict[str, Any]:
        """모델 객체를 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self) -> str:
        """디버깅용 객체 문자열을 반환합니다."""
        cols = []
        for col in self.__table__.columns:
            if col.name in ["embedding", "content", "raw_text"]:
                continue

            val = getattr(self, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            if isinstance(val, str) and len(val) > 20:
                val = val[:17] + "..."

            cols.append(f"{col.name}={val}")

        return f"<{self.__class__.__name__} {', '.join(cols)}>"


class CreatedAtMixin:
    """생성 시각만 필요한 모델용 믹스인."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """생성/수정 시각이 필요한 모델용 믹스인."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )
