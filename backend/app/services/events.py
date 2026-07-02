from typing import Any

from sqlalchemy.orm import Session

from app.models import Event


def log_event(
    db: Session, user_id: int, event_type: str, meta: dict[str, Any] | None = None
) -> None:
    """全学習アクションはこの1関数経由で events に記録する（KPI集計の唯一の元データ）。"""
    db.add(Event(user_id=user_id, type=event_type, meta=meta or {}))
