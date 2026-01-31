from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {}


class TimestampMixin:
    created_at = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
