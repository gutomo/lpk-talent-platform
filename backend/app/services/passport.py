"""Talent Passport の集計サービス。

学生1人の学習データ（発音・会話・面接・模試・出席・態度）を1つの snapshot(jsonb)
に集約し、企業提出用の候補者紹介シートの元データにする。リスクフラグはルールベース。

集計元は各テーブルの生データ。events は最終利用日（未利用日数の判定）にのみ使う。
now は決定的テストのため呼び出し側から渡す（streak / seed と同じ方針）。
snapshot は PDF 生成と共有ビューの両方が参照するので、表示に必要な値は全てここで確定させる。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    AttitudeReview,
    Cohort,
    ConversationSession,
    Enrollment,
    Event,
    InterviewEvaluation,
    InterviewSession,
    InterviewTurn,
    MockSession,
    Passport,
    PronunciationAttempt,
    User,
)
from app.models.enums import Sector, SessionStatus, TurnRole

SNAPSHOT_VERSION = "passport-v1"

# リスク判定のしきい値（BUILD_PLAN Phase 4：出席率80%未満 / スコア下降 / 7日間未利用）。
ATTENDANCE_RISK_THRESHOLD = 80  # 出席率がこれ未満でフラグ
INACTIVE_RISK_DAYS = 7  # 最終利用からこれ以上（日）でフラグ
DECLINE_RISK_MARGIN = 5  # 直近平均が初期平均をこれ以上下回ったらフラグ

# 面接文字起こしの抜粋数（候補者ターンのみ）。企業に人物像を伝える最小限。
TRANSCRIPT_EXCERPT_TURNS = 3
# 弱点語は多すぎると読めないので頻度上位のみ載せる。
WEAK_WORDS_LIMIT = 6

# チェックリスト項目の達成しきい値（PoC の粗い判定。正式な合否ではない）。
PRON_DONE_THRESHOLD = 70
INTERVIEW_DONE_THRESHOLD = 55
ATTITUDE_DONE_THRESHOLD = 70

# 職種別チェックリスト：(key, 日本語ラベル, 判定メトリクス)。
# メトリクスは pronunciation / interview / hourensou / comprehension のいずれか。
_SECTOR_CHECKLISTS: dict[Sector, list[tuple[str, str, str]]] = {
    Sector.KAIGO: [
        ("greeting", "朝の声かけ・あいさつ", "pronunciation"),
        ("vital_terms", "バイタル・介護用語の発音", "pronunciation"),
        ("hourensou", "報連相ができる", "hourensou"),
        ("interview", "模擬面接を合格ラインで完了", "interview"),
    ],
    Sector.FOOD_MANUFACTURING: [
        ("hygiene_terms", "衛生・品質用語の発音", "pronunciation"),
        ("instructions", "作業指示の理解", "comprehension"),
        ("hourensou", "報連相ができる", "hourensou"),
        ("interview", "模擬面接を合格ラインで完了", "interview"),
    ],
    Sector.RESTAURANT: [
        ("serving", "接客あいさつ・敬語", "pronunciation"),
        ("menu_terms", "メニュー・調理用語の発音", "pronunciation"),
        ("hourensou", "報連相ができる", "hourensou"),
        ("interview", "模擬面接を合格ラインで完了", "interview"),
    ],
}
_GENERAL_CHECKLIST: list[tuple[str, str, str]] = [
    ("basic_pron", "基本語の発音", "pronunciation"),
    ("comprehension", "日常会話の理解", "comprehension"),
    ("hourensou", "報連相ができる", "hourensou"),
    ("interview", "模擬面接を合格ラインで完了", "interview"),
]


def jlpt_band(score: int | None) -> str | None:
    """模試スコアから粗く JLPT 帯を推定する（PoC の簡易ルール。正式判定ではない）。"""
    if score is None:
        return None
    if score >= 65:
        return "N4"
    if score >= 45:
        return "N5"
    return "N5未満"


def _aware(dt: datetime | None, ref: datetime) -> datetime | None:
    """naive（SQLite 由来）なら ref のタイムゾーンを付与して aware 同士で比較できるようにする。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ref.tzinfo)
    return dt


def _enrollment_info(db: Session, user_id: int) -> tuple[str | None, Sector | None]:
    """所属コホート名と職種。複数あれば開始日が最新のものを採る。"""
    row = db.execute(
        select(Cohort.name, Cohort.sector)
        .join(Enrollment, Enrollment.cohort_id == Cohort.id)
        .where(Enrollment.user_id == user_id)
        .order_by(Cohort.start_date.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _pronunciation(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(PronunciationAttempt.scores, PronunciationAttempt.weak_words)
        .where(PronunciationAttempt.user_id == user_id)
        .order_by(PronunciationAttempt.created_at)
    ).all()
    if not rows:
        return {
            "attempts": 0,
            "avg_accuracy": None,
            "early_avg": None,
            "recent_avg": None,
            "weak_words": [],
        }
    accs = [int((r.scores or {}).get("accuracy", 0)) for r in rows]
    n = len(accs)
    # 初期1/3 と 直近1/3 の平均で傾向（下降フラグの元）を見る。
    half = max(1, n // 3)
    weak: dict[str, dict[str, int]] = {}
    for r in rows:
        for w in r.weak_words or []:
            word = w.get("word")
            if word is None:
                continue
            entry = weak.setdefault(word, {"word": word, "count": 0, "min_accuracy": 100})
            entry["count"] += 1
            entry["min_accuracy"] = min(entry["min_accuracy"], int(w.get("accuracy", 100)))
    weak_sorted = sorted(weak.values(), key=lambda e: (-e["count"], e["min_accuracy"]))
    return {
        "attempts": n,
        "avg_accuracy": round(sum(accs) / n),
        "early_avg": round(sum(accs[:half]) / half),
        "recent_avg": round(sum(accs[-half:]) / half),
        "weak_words": weak_sorted[:WEAK_WORDS_LIMIT],
    }


def _latest_transcript(db: Session, user_id: int) -> list[str]:
    """直近の完了面接から候補者ターンを数件抜粋する（人物像の補足）。"""
    latest = db.execute(
        select(InterviewSession.id)
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.status == SessionStatus.COMPLETED,
        )
        .order_by(InterviewSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return []
    turns = db.execute(
        select(InterviewTurn.text_ja)
        .where(InterviewTurn.session_id == latest, InterviewTurn.role == TurnRole.CANDIDATE)
        .order_by(InterviewTurn.seq)
    ).scalars().all()
    return list(turns)[:TRANSCRIPT_EXCERPT_TURNS]


def _interview(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(InterviewEvaluation.total, InterviewEvaluation.created_at)
        .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
        .where(InterviewSession.user_id == user_id)
        .order_by(InterviewEvaluation.created_at)
    ).all()
    excerpt = _latest_transcript(db, user_id)
    totals = [r.total for r in rows]
    n = len(totals)
    if n == 0:
        return {
            "sessions": 0,
            "latest_total": None,
            "avg_total": None,
            "early_avg": None,
            "recent_avg": None,
            "trend": [],
            "transcript_excerpt": excerpt,
        }
    half = max(1, n // 3)
    return {
        "sessions": n,
        "latest_total": totals[-1],
        "avg_total": round(sum(totals) / n),
        "early_avg": round(sum(totals[:half]) / half),
        "recent_avg": round(sum(totals[-half:]) / half),
        "trend": [{"date": r.created_at.date().isoformat(), "total": r.total} for r in rows],
        "transcript_excerpt": excerpt,
    }


def _conversation(db: Session, user_id: int) -> dict[str, Any]:
    # 会話練習には数値評価が無いので、完了セッション数を代理指標にする。
    completed = db.execute(
        select(func.count())
        .select_from(ConversationSession)
        .where(
            ConversationSession.user_id == user_id,
            ConversationSession.status == SessionStatus.COMPLETED,
        )
    ).scalar_one()
    return {"completed": int(completed)}


def _japanese_level(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(MockSession.score, MockSession.created_at)
        .where(MockSession.user_id == user_id)
        .order_by(MockSession.created_at)
    ).all()
    trend = [{"date": r.created_at.date().isoformat(), "score": r.score} for r in rows]
    current = jlpt_band(rows[-1].score) if rows else None
    return {"current": current, "trend": trend}


def _attendance(db: Session, user_id: int) -> dict[str, Any]:
    values = db.execute(
        select(AttendanceRecord.value).where(AttendanceRecord.user_id == user_id)
    ).scalars().all()
    if not values:
        return {"rate": None, "records": 0}
    return {"rate": round(sum(values) / len(values)), "records": len(values)}


def _attitude(db: Session, user_id: int) -> dict[str, Any] | None:
    row = db.execute(
        select(AttitudeReview.checklist, AttitudeReview.note, AttitudeReview.created_at)
        .where(AttitudeReview.user_id == user_id)
        .order_by(AttitudeReview.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "checklist": row.checklist or {},
        "note": row.note,
        "reviewed_at": row.created_at.date().isoformat(),
    }


def _last_active(db: Session, user_id: int) -> datetime | None:
    # func.max だと型付けが外れて SQLite が文字列を返すので、型付き列を order+limit で取る。
    return db.execute(
        select(Event.created_at)
        .where(Event.user_id == user_id)
        .order_by(Event.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _metric_done(
    metric: str,
    pron: dict[str, Any],
    itv: dict[str, Any],
    level: dict[str, Any],
    attitude: dict[str, Any] | None,
) -> bool:
    if metric == "pronunciation":
        return pron["avg_accuracy"] is not None and pron["avg_accuracy"] >= PRON_DONE_THRESHOLD
    if metric == "interview":
        return itv["latest_total"] is not None and itv["latest_total"] >= INTERVIEW_DONE_THRESHOLD
    if metric == "hourensou":
        if attitude is None:
            return False
        val = attitude["checklist"].get("hourensou")
        return val is not None and val >= ATTITUDE_DONE_THRESHOLD
    if metric == "comprehension":
        return level["current"] == "N4"
    return False


def _sector_checklist(
    sector: Sector | None,
    pron: dict[str, Any],
    itv: dict[str, Any],
    level: dict[str, Any],
    attitude: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items = _SECTOR_CHECKLISTS.get(sector, _GENERAL_CHECKLIST) if sector else _GENERAL_CHECKLIST
    return [
        {"key": key, "label_ja": label, "done": _metric_done(metric, pron, itv, level, attitude)}
        for key, label, metric in items
    ]


def evaluate_risk(
    *,
    attendance_rate: int | None,
    pron_early: int | None,
    pron_recent: int | None,
    itv_early: int | None,
    itv_recent: int | None,
    last_active: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    """ルールベースのリスク判定。1つでもフラグが立てば level=risk。

    - low_attendance：出席率 < 80%
    - score_decline：発音 or 面接の直近平均が初期平均を DECLINE_RISK_MARGIN 以上下回る
    - inactive：最終利用から INACTIVE_RISK_DAYS 日以上、または利用記録なし
    """
    flags: list[str] = []
    if attendance_rate is not None and attendance_rate < ATTENDANCE_RISK_THRESHOLD:
        flags.append("low_attendance")

    declined = False
    if (
        pron_recent is not None
        and pron_early is not None
        and pron_recent < pron_early - DECLINE_RISK_MARGIN
    ):
        declined = True
    if (
        itv_recent is not None
        and itv_early is not None
        and itv_recent < itv_early - DECLINE_RISK_MARGIN
    ):
        declined = True
    if declined:
        flags.append("score_decline")

    if last_active is None or (now - last_active).days >= INACTIVE_RISK_DAYS:
        flags.append("inactive")

    return {"flags": flags, "level": "risk" if flags else "none"}


def build_snapshot(db: Session, student: User, now: datetime) -> dict[str, Any]:
    """学生1人分の Passport snapshot(jsonb) を組み立てる。"""
    cohort_name, sector = _enrollment_info(db, student.id)
    pron = _pronunciation(db, student.id)
    conv = _conversation(db, student.id)
    itv = _interview(db, student.id)
    level = _japanese_level(db, student.id)
    attendance = _attendance(db, student.id)
    attitude = _attitude(db, student.id)
    checklist = _sector_checklist(sector, pron, itv, level, attitude)
    risk = evaluate_risk(
        attendance_rate=attendance["rate"],
        pron_early=pron["early_avg"],
        pron_recent=pron["recent_avg"],
        itv_early=itv["early_avg"],
        itv_recent=itv["recent_avg"],
        last_active=_aware(_last_active(db, student.id), now),
        now=now,
    )
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "generated_at": now.isoformat(),
        "student": {
            "name": student.name,
            "cohort": cohort_name,
            "sector": sector.value if sector is not None else None,
        },
        "japanese_level": level,
        "pronunciation": pron,
        "conversation": conv,
        "interview": itv,
        "attendance": attendance,
        "attitude": attitude,
        "checklist": checklist,
        "risk": risk,
    }


def create_passport(db: Session, student: User, now: datetime) -> Passport:
    """最新 snapshot を確定し、version を1つ進めて Passport 行を追加する（commit は呼び出し側）。"""
    snapshot = build_snapshot(db, student, now)
    max_version = db.execute(
        select(func.max(Passport.version)).where(Passport.user_id == student.id)
    ).scalar_one_or_none()
    passport = Passport(
        user_id=student.id,
        version=(max_version or 0) + 1,
        snapshot=snapshot,
        pdf_ref=None,
    )
    db.add(passport)
    return passport
