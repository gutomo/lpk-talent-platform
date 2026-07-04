from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SessionMode


class QueueItemOut(BaseModel):
    """添削キュー1行。未確認の面接評価を古い順に並べる。"""

    evaluation_id: int
    session_id: int
    student_id: int
    student_name: str
    scenario: str
    title_ja: str | None
    mode: SessionMode
    total: int
    created_at: datetime
    waiting_days: int


class ReviewCompleteOut(BaseModel):
    evaluation_id: int
    reviewed_at: datetime
    reviewer_id: int
