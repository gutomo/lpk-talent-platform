from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import CreatedAtMixin, str_enum
from app.models.enums import AttendanceKind


class AttendanceRecord(CreatedAtMixin, Base):
    """value は常に 0〜100 の出席率。daily は出席=100、欠席=0 で記録し、平均が期間出席率になる。"""

    __tablename__ = "attendance_records"
    __table_args__ = (
        CheckConstraint("value >= 0 AND value <= 100", name="value_range"),
        UniqueConstraint("user_id", "kind", "record_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[AttendanceKind] = mapped_column(str_enum(AttendanceKind, "attendance_kind"))
    record_date: Mapped[date] = mapped_column(Date)
    value: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(255))


class AttitudeReview(CreatedAtMixin, Base):
    __tablename__ = "attitude_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # 報連相・時間厳守・寮生活・マナー等5項目のチェックリスト。項目スキーマはサービス層で検証する。
    checklist: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
