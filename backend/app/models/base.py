"""SQLAlchemy declarative base + common mixins."""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def pg_enum(enum_cls: type[Enum], *, name: str) -> SAEnum:
    """Postgres-native ENUM bound to enum *values* (lowercase) — not Python member names."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda x: [e.value for e in x],
        native_enum=True,
        create_type=False,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Project SQLAlchemy base. All models inherit."""

    type_annotation_map: dict[type, Any] = {}


class TimestampMixin:
    """Adds created_at + updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


def new_uuid() -> UUID:
    return uuid4()
