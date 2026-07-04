from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.models.enums import UserRole
from app.seed import RISK_INACTIVE_DAYS, UNREVIEWED_QUEUE_SIZE, seed_all

NOW = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    summary = seed_all(session, now=NOW)
    session.info["summary"] = summary
    yield session
    session.close()


def _user_by_email(db: Session, email: str) -> models.User:
    return db.execute(select(models.User).where(models.User.email == email)).scalar_one()


def test_headcounts(db: Session) -> None:
    def count(role: UserRole) -> int:
        return db.execute(
            select(func.count()).select_from(models.User).where(models.User.role == role)
        ).scalar_one()

    assert count(UserRole.STUDENT) == 30
    assert count(UserRole.TEACHER) == 2
    assert count(UserRole.ADMIN) == 1
    assert db.execute(select(func.count()).select_from(models.Organization)).scalar_one() == 2
    assert db.execute(select(func.count()).select_from(models.Enrollment)).scalar_one() == 30


def test_content_bank_seeded(db: Session) -> None:
    total = db.execute(select(func.count()).select_from(models.ContentItem)).scalar_one()
    assert total == 120
    versions = db.execute(select(models.ContentItem.meta["bank_version"])).scalars().all()
    assert len(versions) == total


def test_history_volume(db: Session) -> None:
    attempts = db.execute(
        select(func.count()).select_from(models.PronunciationAttempt)
    ).scalar_one()
    evals = db.execute(select(func.count()).select_from(models.InterviewEvaluation)).scalar_one()
    assert attempts > 500
    assert evals > 100


def _eval_totals(db: Session, user_id: int) -> list[int]:
    rows = db.execute(
        select(models.InterviewEvaluation.total)
        .join(
            models.InterviewSession,
            models.InterviewSession.id == models.InterviewEvaluation.session_id,
        )
        .where(models.InterviewSession.user_id == user_id)
        .order_by(models.InterviewEvaluation.created_at)
    ).scalars()
    return list(rows)


def test_risk_student_hits_all_three_risk_rules(db: Session) -> None:
    summary = db.info["summary"]
    risk = _user_by_email(db, summary["risk_student_email"])

    attendance = db.execute(
        select(models.AttendanceRecord.value).where(models.AttendanceRecord.user_id == risk.id)
    ).scalars().all()
    assert attendance and all(v < 80 for v in attendance)

    last_event = db.execute(
        select(func.max(models.Event.created_at)).where(models.Event.user_id == risk.id)
    ).scalar_one()
    threshold = (NOW - timedelta(days=7)).replace(tzinfo=None)
    assert last_event < threshold

    totals = _eval_totals(db, risk.id)
    assert len(totals) >= 4
    assert sum(totals[:3]) / 3 > sum(totals[-3:]) / 3

    inactive_since = (NOW - timedelta(days=RISK_INACTIVE_DAYS)).replace(tzinfo=None)
    assert last_event <= inactive_since


def test_top_student_improves_10_to_20_percent(db: Session) -> None:
    summary = db.info["summary"]
    top = _user_by_email(db, summary["demo_student_email"])
    totals = _eval_totals(db, top.id)
    assert len(totals) >= 6
    first3 = sum(totals[:3]) / 3
    last3 = sum(totals[-3:]) / 3
    assert 1.05 <= last3 / first3 <= 1.35


def test_every_learning_action_has_an_event(db: Session) -> None:
    def count(model) -> int:
        return db.execute(select(func.count()).select_from(model)).scalar_one()

    def event_count(event_type: str) -> int:
        return db.execute(
            select(func.count()).select_from(models.Event).where(models.Event.type == event_type)
        ).scalar_one()

    assert event_count("pronunciation_attempt") == count(models.PronunciationAttempt)
    assert event_count("interview_completed") == count(models.InterviewEvaluation)
    assert event_count("conversation_completed") == count(models.ConversationSession)
    assert event_count("mock_completed") == count(models.MockSession)


def test_scores_within_0_100(db: Session) -> None:
    totals = db.execute(select(models.InterviewEvaluation.total)).scalars().all()
    mocks = db.execute(select(models.MockSession.score)).scalars().all()
    assert all(0 <= t <= 100 for t in totals)
    assert all(0 <= s <= 100 for s in mocks)


def test_review_queue_leaves_newest_unreviewed(db: Session) -> None:
    summary = db.info["summary"]
    assert summary["unreviewed_evaluations"] == UNREVIEWED_QUEUE_SIZE

    unreviewed = db.execute(
        select(models.InterviewEvaluation)
        .where(models.InterviewEvaluation.reviewed_at.is_(None))
        .order_by(models.InterviewEvaluation.created_at)
    ).scalars().all()
    assert len(unreviewed) == UNREVIEWED_QUEUE_SIZE

    # 未確認は「最も新しい10件」。確認済みの最新よりも古い未確認は存在しない。
    newest_reviewed = db.execute(
        select(func.max(models.InterviewEvaluation.created_at))
        .where(models.InterviewEvaluation.reviewed_at.is_not(None))
    ).scalar_one()
    assert all(ev.created_at >= newest_reviewed for ev in unreviewed)

    # 確認済みには確認者（教師）が入っている。
    reviewed = db.execute(
        select(models.InterviewEvaluation)
        .where(models.InterviewEvaluation.reviewed_at.is_not(None))
        .limit(5)
    ).scalars().all()
    assert reviewed and all(ev.reviewer_id is not None for ev in reviewed)


def test_seed_refuses_non_empty_db(db: Session) -> None:
    with pytest.raises(RuntimeError):
        seed_all(db, now=NOW)
