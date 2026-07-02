"""streak（連続利用日数）の算出。events テーブルが唯一の元データ。

学生はインドネシア在住のため、日付の境界は WIB（UTC+7）で判定する。
今日まだ利用していなくても、昨日までの連続は「継続中」として数える
（今日中に使えば途切れないため）。
"""

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event

WIB = timezone(timedelta(hours=7))


def _to_wib_date(created_at: datetime) -> date:
    # SQLite（テスト）は naive で返るので UTC とみなす。Postgres は aware。
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone(WIB).date()


def current_streak(db: Session, user_id: int, today: date | None = None) -> dict[str, object]:
    """{"days": 連続日数, "active_today": 今日の利用有無} を返す。"""
    if today is None:
        today = datetime.now(UTC).astimezone(WIB).date()
    rows = db.execute(select(Event.created_at).where(Event.user_id == user_id)).scalars()
    days = {_to_wib_date(created_at) for created_at in rows}

    active_today = today in days
    cursor = today if active_today else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return {"days": streak, "active_today": active_today}
