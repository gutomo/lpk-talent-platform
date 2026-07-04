"""ダッシュボード用のバッチ集計サービス。

教師のクラス一覧と経営者KPIの元データを、組織単位で数本のクエリにまとめて集計する。
学生30〜50名規模の PoC でも学生ごとに build_snapshot を回すと N+1 が重いのと、
何より数式を snapshot と二重定義するとダッシュボードと Passport の数値がズレるため、
判定・平均は passport.py の純関数（attendance_rate_of / early_recent_avgs /
evaluate_risk）を共用する。now は決定的テストのため呼び出し側から渡す。
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    Event,
    InterviewEvaluation,
    InterviewSession,
    MockSession,
    PronunciationAttempt,
    User,
)
from app.models.enums import UserRole
from app.services.passport import (
    attendance_rate_of,
    early_recent_avgs,
    ensure_aware,
    evaluate_risk,
    jlpt_band,
)

# 経営者KPIの定義値。BUILD_PLAN の KPI 表と同一定義（Phase 6 も同じ値を使う）。
TREND_WEEKS = 8
AI_USAGE_TARGET_DAYS = 3  # 「学生のAI利用率：週3回以上」
INTERVIEW_TARGET_SESSIONS = 10  # 「面接練習回数：1人10回以上」
IMPROVEMENT_WINDOW = 3  # 「模擬面接スコア：初回3回平均 vs 直近3回平均」


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


def _interview_totals_by_user(db: Session, student_ids: list[int]) -> dict[int, list[int]]:
    """学生ごとの面接評価 total を時系列昇順で返す。クラス一覧と経営者KPIが共用する。"""
    totals: dict[int, list[int]] = {}
    for user_id, total in db.execute(
        select(InterviewSession.user_id, InterviewEvaluation.total)
        .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
        .where(InterviewSession.user_id.in_(student_ids))
        .order_by(InterviewEvaluation.created_at, InterviewEvaluation.id)
    ):
        totals.setdefault(user_id, []).append(total)
    return totals


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

    itv_by_user = _interview_totals_by_user(db, student_ids)

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


def _avg(values: list) -> float | None:
    return sum(values) / len(values) if values else None


def admin_kpi(db: Session, org_id: int, now: datetime) -> dict[str, Any]:
    """経営者ダッシュボードのKPI集計。BUILD_PLAN の KPI 表と同一定義。

    時刻の週次バケット詰めは Python 側で行う。SQLite（テスト）は datetime を
    naive 文字列で返すため、SQL の日時比較・集計は方言差の地雷になる（ensure_aware 参照）。
    PoC 規模（学生50名 × 60日）では全行読みで十分軽い。
    """
    student_ids = _org_student_ids(db, org_id)
    overview = class_overview(db, org_id, now)
    n_students = len(student_ids)

    names = (
        dict(db.execute(select(User.id, User.name).where(User.id.in_(student_ids))).all())
        if student_ids
        else {}
    )
    risk_students = sorted(
        (
            {"id": sid, "name": names.get(sid, ""), "flags": data["risk_flags"]}
            for sid, data in overview.items()
            if data["risk_level"] == "risk"
        ),
        key=lambda s: s["name"],
    )

    att_rates = [
        d["attendance_rate"] for d in overview.values() if d["attendance_rate"] is not None
    ]
    attendance_avg = round(_avg(att_rates)) if att_rates else None

    # 模試：全記録を1クエリで読み、per学生の推移と週次バケットの両方に使う。
    week0 = now - timedelta(weeks=TREND_WEEKS)
    mock_by_user: dict[int, list[int]] = {}
    weekly_mock: list[list[int]] = [[] for _ in range(TREND_WEEKS)]
    if student_ids:
        for user_id, score, created_at in db.execute(
            select(MockSession.user_id, MockSession.score, MockSession.created_at)
            .where(MockSession.user_id.in_(student_ids))
            .order_by(MockSession.created_at, MockSession.id)
        ):
            mock_by_user.setdefault(user_id, []).append(score)
            created = ensure_aware(created_at, now)
            idx = (created - week0).days // 7
            if 0 <= idx < TREND_WEEKS:
                weekly_mock[idx].append(score)

    latest_scores = [scores[-1] for scores in mock_by_user.values()]
    mock_avg = round(_avg(latest_scores)) if latest_scores else None
    n4_count = sum(1 for s in latest_scores if jlpt_band(s) == "N4")
    n4_rate = round(100 * n4_count / n_students) if n_students else 0

    mock_earlies: list[int] = []
    mock_recents: list[int] = []
    for scores in mock_by_user.values():
        early, recent = early_recent_avgs(scores)
        if early is not None and recent is not None:
            mock_earlies.append(early)
            mock_recents.append(recent)
    mock_early_avg = round(_avg(mock_earlies)) if mock_earlies else None
    mock_recent_avg = round(_avg(mock_recents)) if mock_recents else None

    # 面接：平均回数、目標到達数、初回3回 vs 直近3回の平均改善率。
    itv_by_user = _interview_totals_by_user(db, student_ids)
    total_sessions = sum(len(v) for v in itv_by_user.values())
    interview_avg_sessions = round(total_sessions / n_students, 1) if n_students else 0.0
    interview_target_met = sum(
        1 for v in itv_by_user.values() if len(v) >= INTERVIEW_TARGET_SESSIONS
    )
    improvements: list[float] = []
    for totals in itv_by_user.values():
        if len(totals) < IMPROVEMENT_WINDOW * 2:
            continue
        early = _avg(totals[:IMPROVEMENT_WINDOW])
        recent = _avg(totals[-IMPROVEMENT_WINDOW:])
        if early:
            improvements.append((recent - early) / early * 100)
    interview_improvement_pct = round(_avg(improvements)) if improvements else None

    # 学習イベント：週次トレンドと「週3日以上利用」の両方をこの読みから出す。
    seven_days_ago = now - timedelta(days=7)
    weekly_events = [0] * TREND_WEEKS
    weekly_active: list[set[int]] = [set() for _ in range(TREND_WEEKS)]
    active_days: dict[int, set[str]] = {}
    practice_events_7d = 0
    if student_ids:
        for user_id, created_at in db.execute(
            select(Event.user_id, Event.created_at).where(Event.user_id.in_(student_ids))
        ):
            created = ensure_aware(created_at, now)
            idx = (created - week0).days // 7
            if 0 <= idx < TREND_WEEKS:
                weekly_events[idx] += 1
                weekly_active[idx].add(user_id)
            if created >= seven_days_ago:
                practice_events_7d += 1
                active_days.setdefault(user_id, set()).add(created.date().isoformat())
    ai_usage_students = sum(
        1 for days in active_days.values() if len(days) >= AI_USAGE_TARGET_DAYS
    )
    ai_usage_rate = round(100 * ai_usage_students / n_students) if n_students else 0

    # 添削キュー滞留（KPI「先生の添削時間」の参考値）。
    pending_created = [
        ensure_aware(created_at, now)
        for created_at in db.execute(
            select(InterviewEvaluation.created_at)
            .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
            .join(User, User.id == InterviewSession.user_id)
            .where(
                User.org_id == org_id,
                User.role == UserRole.STUDENT,
                InterviewEvaluation.reviewed_at.is_(None),
            )
        ).scalars()
    ]
    waiting = [max(0, (now - created).days) for created in pending_created]
    review_avg_waiting_days = round(_avg(waiting), 1) if waiting else None

    weekly = [
        {
            "week_start": (week0 + timedelta(weeks=i)).date(),
            "events": weekly_events[i],
            "active_students": len(weekly_active[i]),
            "mock_avg": round(_avg(weekly_mock[i])) if weekly_mock[i] else None,
        }
        for i in range(TREND_WEEKS)
    ]

    return {
        "students": n_students,
        "risk_students": risk_students,
        "n4_rate": n4_rate,
        "mock_avg": mock_avg,
        "attendance_avg": attendance_avg,
        "practice_events_7d": practice_events_7d,
        "weekly": weekly,
        "kpi_cards": {
            "ai_usage_students": ai_usage_students,
            "ai_usage_rate": ai_usage_rate,
            "interview_avg_sessions": interview_avg_sessions,
            "interview_target_met": interview_target_met,
            "interview_improvement_pct": interview_improvement_pct,
            "mock_early_avg": mock_early_avg,
            "mock_recent_avg": mock_recent_avg,
            "review_pending": len(waiting),
            "review_avg_waiting_days": review_avg_waiting_days,
        },
    }
