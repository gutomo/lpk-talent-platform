import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Postgres では JSONB、それ以外（テスト用 SQLite）では JSON。本番 DDL は JSONB のまま。
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


def str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    # native_enum=False renders VARCHAR + CHECK so enum changes stay plain migrations.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
