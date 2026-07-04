"""ダッシュボード用のバッチ集計サービス。

教師のクラス一覧と経営者KPIの元データを、組織単位で数本のクエリにまとめて集計する。
学生30〜50名規模の PoC でも学生ごとに build_snapshot を回すと N+1 が重いのと、
何より数式を snapshot と二重定義するとダッシュボードと Passport の数値がズレるため、
判定・平均は passport.py の純関数（attendance_rate_of / early_recent_avgs /
evaluate_risk）を共用する。now は決定的テストのため呼び出し側から渡す。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    Event,
    InterviewEvaluation,
    InterviewSession,
    PronunciationAttempt,
    User,
)
from app.models.enums import UserRole
from app.services.passport import (
    attendance_rate_of,
    early_recent_avgs,
    ensure_aware,
    evaluate_risk,
)


def _org_student_ids(db: Session, org_id: int) -> list[int]:
    return list(
        db.execute(
            select(User.id).where(User.role == UserRole.STUDENT, User.org_id == org_id)
        ).scalars()
    )


def _last_active_map(db: Session, student_ids: list[int]) -> dict[int, datetime]:
    """学生ごとの最終イベント日時。

    func.max(created_at) を直接 SELECT すると SQLite では文字列になるため
    （passport._last_active と同じ理由）、max との自己結合で型付き列を取る。
    """
    last_event = (
        select(Event.user_id, func.max(Event.created_at).label("last_at"))
        .where(Event.user_id.in_(student_ids))
        .group_by(Event.user_id)
        .subquery()
    )
    rows = db.execute(
        select(Event.user_id, Event.created_at).join(
            last_event,
            (Event.user_id == last_event.c.user_id)
            & (Event.created_at == last_event.c.last_at),
        )
    )
    # 同時刻のイベントが複数あっても値は同じなので上書きで問題ない。
    return {user_id: created_at for user_id, created_at in rows}


def class_overview(db: Session, org_id: int, now: datetime) -> dict[int, dict[str, Any]]:
    """クラス一覧用の学生別集計。{user_id: {進捗指標とリスク判定}} を返す。"""
    student_ids = _org_student_ids(db, org_id)
    if not student_ids:
        return {}

    last_active = _last_active_map(db, student_ids)

    att_by_user: dict[int, list[tuple[Any, Any, int]]] = {}
    for user_id, kind, record_date, value in db.execute(
        select(
            AttendanceRecord.user_id,
            AttendanceRecord.kind,
            AttendanceRecord.record_date,
            AttendanceRecord.value,
        ).where(AttendanceRecord.user_id.in_(student_ids))
    ):
        att_by_user.setdefault(user_id, []).append((kind, record_date, value))

    itv_by_user: dict[int, list[int]] = {}
    for user_id, total in db.execute(
        select(InterviewSession.user_id, InterviewEvaluation.total)
        .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
        .where(InterviewSession.user_id.in_(student_ids))
        .order_by(InterviewEvaluation.created_at, InterviewEvaluation.id)
    ):
        itv_by_user.setdefault(user_id, []).append(total)

    pron_by_user: dict[int, list[int]] = {}
    for user_id, scores in db.execute(
        select(PronunciationAttempt.user_id, PronunciationAttempt.scores)
        .where(PronunciationAttempt.user_id.in_(student_ids))
        .order_by(PronunciationAttempt.created_at, PronunciationAttempt.id)
    ):
        pron_by_user.setdefault(user_id, []).append(int((scores or {}).get("accuracy", 0)))

    overview: dict[int, dict[str, Any]] = {}
    for sid in student_ids:
        att_rate = attendance_rate_of(att_by_user.get(sid, []))
        totals = itv_by_user.get(sid, [])
        itv_early, itv_recent = early_recent_avgs(totals)
        accs = pron_by_user.get(sid, [])
        pron_early, pron_recent = early_recent_avgs(accs)
        risk = evaluate_risk(
            attendance_rate=att_rate,
            pron_early=pron_early,
            pron_recent=pron_recent,
            itv_early=itv_early,
            itv_recent=itv_recent,
            last_active=ensure_aware(last_active.get(sid), now),
            now=now,
        )
        overview[sid] = {
            "attendance_rate": att_rate,
            "interview_sessions": len(totals),
            "interview_latest_total": totals[-1] if totals else None,
            "pron_avg_accuracy": round(sum(accs) / len(accs)) if accs else None,
            "risk_flags": risk["flags"],
            "risk_level": risk["level"],
        }
    return overview
