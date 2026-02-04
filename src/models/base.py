from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {}

    id: Any

    def to_dict(self) -> dict[str, Any]:
        """
        모델 객체를 딕셔너리로 변환 (Pydantic 변환이나 로깅에 유용)
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self) -> str:
        """
        디버깅 시 객체의 주요 정보를 문자열로 반환
        예: <Company id=1 name='Samsung' ...>
        """
        cols = []
        for col in self.__table__.columns:
            # 임베딩 벡터나 너무 긴 텍스트는 로그 가독성을 해치므로 제외
            if col.name in ["embedding", "content", "raw_text"]:
                continue

            val = getattr(self, col.name)
            # 날짜나 너무 긴 값은 포맷팅
            if isinstance(val, datetime):
                val = val.isoformat()
            if isinstance(val, str) and len(val) > 20:
                val = val[:17] + "..."

            cols.append(f"{col.name}={val}")

        return f"<{self.__class__.__name__} {', '.join(cols)}>"


class CreatedAtMixin:
    """생성 시간만 필요한 경우 (예: 로그, 이력 테이블)"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """수정 시간도 필요한 경우 (예: 회원, 게시글)"""

    # CreatedAtMixin을 상속받았으므로 created_at은 자동으로 포함됨
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=True
    )
