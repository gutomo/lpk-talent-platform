from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import CreatedAtMixin, PortableJSON


class Event(CreatedAtMixin, Base):
    """全学習アクションの記録。KPI集計の唯一の元データ。"""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(64), index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
