import uuid
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


_E = TypeVar("_E", bound=StrEnum)


def pg_enum(enum_cls: type[_E], name: str) -> SAEnum:
    """SQLAlchemy's Enum type defaults to storing a Python Enum's *name*
    (e.g. "ADMIN"), not its *value* — surprising for a StrEnum, where
    `str(member) == member.value` (e.g. "admin") everywhere else in the
    codebase, including the Postgres enum type Alembic migrations create
    with the lowercase values. Without `values_callable` here, inserts fail
    against a real Postgres enum column with "invalid input value for enum"
    even though SQLite-backed tests pass (SQLite's CHECK constraint is
    derived from the same default and is self-consistent, so it never
    surfaces the mismatch). Every enum-backed column must use this helper.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


__all__ = ["Base", "TimestampMixin", "UUIDPrimaryKeyMixin", "pg_enum"]
