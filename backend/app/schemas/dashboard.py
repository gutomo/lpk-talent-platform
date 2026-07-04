from datetime import date

from pydantic import BaseModel


class RiskStudentOut(BaseModel):
    """アラートバッジ用のリスク学生1名分。"""

    id: int
    name: str
    flags: list[str]


class WeeklyPointOut(BaseModel):
    """週次トレンド1週分。week_start はその週の開始日（now - 8週から7日刻み）。"""

    week_start: date
    events: int
    active_students: int
    mock_avg: int | None


class KpiCardsOut(BaseModel):
    """PoC KPI カード。定義は BUILD_PLAN の KPI 表と同一。"""

    ai_usage_students: int
    ai_usage_rate: int
    interview_avg_sessions: float
    interview_target_met: int
    interview_improvement_pct: int | None
    mock_early_avg: int | None
    mock_recent_avg: int | None
    review_pending: int
    review_avg_waiting_days: float | None


class AdminKpiOut(BaseModel):
    students: int
    risk_students: list[RiskStudentOut]
    n4_rate: int
    mock_avg: int | None
    attendance_avg: int | None
    practice_events_7d: int
    weekly: list[WeeklyPointOut]
    kpi_cards: KpiCardsOut
