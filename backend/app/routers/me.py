from fastapi import APIRouter
from pydantic import BaseModel

from app.routers.deps import CurrentUser, DbSession
from app.services.streak import current_streak

router = APIRouter(prefix="/me", tags=["me"])


class StreakOut(BaseModel):
    days: int
    active_today: bool


@router.get("/streak")
def get_streak(user: CurrentUser, db: DbSession) -> StreakOut:
    """ログイン中ユーザーの連続利用日数（WIB基準、events 由来）。"""
    result = current_streak(db, user.id)
    return StreakOut(days=result["days"], active_today=result["active_today"])
