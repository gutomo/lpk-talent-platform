from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import (
    AttendanceKind,
    Locale,
    OrgType,
    Sector,
    SessionMode,
    SessionStatus,
    TurnRole,
    UserRole,
)
from app.services.auth import hash_password
from app.services.passport import build_snapshot, evaluate_risk

PASSWORD = "rahasia123"


def _days_ago(now: datetime, k: int) -> datetime:
    return now - timedelta(days=k)


@pytest.fixture()
def ctx():
    """1組織に健全な学生(siti)とリスク学生(doni)、別組織の学生(dewi)を仕込む。

    時刻は実行時の now を基準にする（ルータは datetime.now(UTC) を使うため、
    最終利用の未利用日数判定が実クロックに依存せず安定する）。
    """
    now = datetime.now(UTC)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    pw = hash_password(PASSWORD)

    with factory() as db:
        lpk = models.Organization(name="LPK Test", type=OrgType.LPK)
        other = models.Organization(name="LPK Lain", type=OrgType.LPK)
        db.add_all([lpk, other])
        db.flush()

        teacher = models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                              name="田中 美咲", email="teacher@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        doni = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Doni Prasetyo", email="doni@example.com", password_hash=pw)
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([teacher, siti, doni, dewi])
        db.flush()

        cohort = models.Cohort(org_id=lpk.id, name="2026年4月期 介護コース",
                               sector=Sector.KAIGO, start_date=_days_ago(now, 90).date())
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=doni.id))

        # --- 健全な学生 siti：発音・面接が上昇、出席良好、直近利用あり ---
        pron_healthy = [(60, 60, [{"word": "検温", "accuracy": 55}]),
                        (50, 66, [{"word": "検温", "accuracy": 58},
                                  {"word": "手すり", "accuracy": 60}]),
                        (40, 72, []), (30, 78, []), (20, 84, []), (10, 90, [])]
        for ago, acc, weak in pron_healthy:
            db.add(models.PronunciationAttempt(
                user_id=siti.id, item_id=1,
                scores={"accuracy": acc, "fluency": acc, "completeness": acc},
                weak_words=weak, created_at=_days_ago(now, ago),
            ))
        for i, (ago, total) in enumerate([(50, 50), (35, 55), (20, 62), (8, 70)]):
            sess = models.InterviewSession(
                user_id=siti.id, scenario="kaigo_interview", sector=Sector.KAIGO,
                mode=SessionMode.VOICE, status=SessionStatus.COMPLETED,
                created_at=_days_ago(now, ago),
            )
            db.add(sess)
            db.flush()
            if i == 3:  # 直近セッションにだけ文字起こしを入れる
                turns = [
                    (TurnRole.INTERVIEWER, "自己紹介をお願いします。"),
                    (TurnRole.CANDIDATE, "はじめまして。よろしくお願いします。"),
                    (TurnRole.INTERVIEWER, "志望動機は。"),
                    (TurnRole.CANDIDATE, "介護の仕事を学びたいです。"),
                    (TurnRole.INTERVIEWER, "困ったら。"),
                    (TurnRole.CANDIDATE, "すぐに報告します。"),
                ]
                for seq, (role, text) in enumerate(turns, start=1):
                    db.add(models.InterviewTurn(session_id=sess.id, seq=seq, role=role,
                                                text_ja=text, stt=None))
            db.add(models.InterviewEvaluation(
                session_id=sess.id, rubric_version="test-v0",
                scores={"japanese": total}, feedback={}, total=total,
                created_at=_days_ago(now, ago),
            ))
        for ago in (15, 5):
            db.add(models.ConversationSession(
                user_id=siti.id, scenario="morning_greeting", sector=Sector.KAIGO,
                mode=SessionMode.VOICE, status=SessionStatus.COMPLETED,
                created_at=_days_ago(now, ago),
            ))
        for ago, score in [(55, 48), (40, 55), (25, 62), (10, 68)]:
            db.add(models.MockSession(user_id=siti.id, score=score, num_questions=25,
                                      num_correct=score // 4, meta={},
                                      created_at=_days_ago(now, ago)))
        for ago, value in [(60, 90), (30, 92)]:
            db.add(models.AttendanceRecord(user_id=siti.id, kind=AttendanceKind.MONTHLY,
                                           record_date=_days_ago(now, ago).date(), value=value))
        db.add(models.AttitudeReview(
            user_id=siti.id, reviewer_id=teacher.id,
            checklist={"hourensou": 80, "punctuality": 85, "dormitory": 82,
                       "manner": 88, "teamwork": 80},
            note="真面目に取り組んでいます。", created_at=_days_ago(now, 20)))
        db.add(models.Event(user_id=siti.id, type="login", meta={},
                            created_at=_days_ago(now, 1)))

        # --- リスク学生 doni：発音下降、出席低、20日未利用 ---
        for ago, acc in [(40, 70), (30, 66), (22, 60), (20, 52)]:
            db.add(models.PronunciationAttempt(
                user_id=doni.id, item_id=1,
                scores={"accuracy": acc, "fluency": acc, "completeness": acc},
                weak_words=[], created_at=_days_ago(now, ago)))
        for ago, score in [(30, 50), (20, 45)]:
            db.add(models.MockSession(user_id=doni.id, score=score, num_questions=25,
                                      num_correct=score // 4, meta={},
                                      created_at=_days_ago(now, ago)))
        for ago, value in [(60, 70), (30, 74)]:
            db.add(models.AttendanceRecord(user_id=doni.id, kind=AttendanceKind.MONTHLY,
                                           record_date=_days_ago(now, ago).date(), value=value))
        db.add(models.AttitudeReview(
            user_id=doni.id, reviewer_id=teacher.id,
            checklist={"hourensou": 55, "punctuality": 50, "dormitory": 60,
                       "manner": 58, "teamwork": 52},
            note="遅刻が増えています。要面談。", created_at=_days_ago(now, 20)))
        db.add(models.Event(user_id=doni.id, type="login", meta={},
                            created_at=_days_ago(now, 20)))

        db.commit()
        ns = SimpleNamespace(
            factory=factory, now=now,
            siti_id=siti.id, doni_id=doni.id, dewi_id=dewi.id,
        )
    return ns


@pytest.fixture()
def client(ctx):
    def override_get_db():
        db = ctx.factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, email: str) -> None:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


# --------------------------------------------------------------- evaluate_risk

def test_risk_clean_when_all_good() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)
    risk = evaluate_risk(
        attendance_rate=95, pron_early=60, pron_recent=80,
        itv_early=55, itv_recent=70, last_active=now - timedelta(days=1), now=now,
    )
    assert risk == {"flags": [], "level": "none"}


def test_risk_flags_each_rule() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)
    risk = evaluate_risk(
        attendance_rate=72, pron_early=70, pron_recent=52,
        itv_early=None, itv_recent=None, last_active=now - timedelta(days=20), now=now,
    )
    assert set(risk["flags"]) == {"low_attendance", "score_decline", "inactive"}
    assert risk["level"] == "risk"


def test_risk_inactive_when_no_activity() -> None:
    now = datetime(2026, 7, 3, tzinfo=UTC)
    risk = evaluate_risk(
        attendance_rate=90, pron_early=None, pron_recent=None,
        itv_early=None, itv_recent=None, last_active=None, now=now,
    )
    assert risk["flags"] == ["inactive"]


# --------------------------------------------------------------- build_snapshot

def test_snapshot_healthy_student(ctx) -> None:
    with ctx.factory() as db:
        student = db.get(models.User, ctx.siti_id)
        snap = build_snapshot(db, student, ctx.now)

    assert snap["snapshot_version"] == "passport-v1"
    assert snap["student"]["sector"] == "kaigo"
    assert snap["student"]["cohort"] == "2026年4月期 介護コース"

    assert snap["pronunciation"]["attempts"] == 6
    assert snap["pronunciation"]["avg_accuracy"] == 75
    assert snap["pronunciation"]["early_avg"] == 63
    assert snap["pronunciation"]["recent_avg"] == 87
    assert snap["pronunciation"]["weak_words"][0] == {
        "word": "検温", "count": 2, "min_accuracy": 55
    }

    assert snap["interview"]["sessions"] == 4
    assert snap["interview"]["latest_total"] == 70
    assert snap["interview"]["avg_total"] == 59
    assert snap["interview"]["transcript_excerpt"] == [
        "はじめまして。よろしくお願いします。",
        "介護の仕事を学びたいです。",
        "すぐに報告します。",
    ]

    assert snap["conversation"]["completed"] == 2
    assert snap["japanese_level"]["current"] == "N4"
    assert len(snap["japanese_level"]["trend"]) == 4
    assert snap["attendance"]["rate"] == 91
    assert all(item["done"] for item in snap["checklist"])
    assert snap["risk"] == {"flags": [], "level": "none"}


def test_snapshot_risk_student(ctx) -> None:
    with ctx.factory() as db:
        student = db.get(models.User, ctx.doni_id)
        snap = build_snapshot(db, student, ctx.now)

    assert snap["pronunciation"]["early_avg"] == 70
    assert snap["pronunciation"]["recent_avg"] == 52
    assert snap["interview"]["sessions"] == 0
    assert snap["interview"]["latest_total"] is None
    assert snap["japanese_level"]["current"] == "N5"
    assert snap["attendance"]["rate"] == 72
    assert set(snap["risk"]["flags"]) == {"low_attendance", "score_decline", "inactive"}
    assert snap["risk"]["level"] == "risk"
    assert not any(item["done"] for item in snap["checklist"])


# --------------------------------------------------------------------- router

def test_generate_requires_auth(client: TestClient, ctx) -> None:
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 401


def test_generate_rejects_student_role(client: TestClient, ctx) -> None:
    login(client, "siti@example.com")
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 403


def test_generate_cross_org_student_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.dewi_id}").status_code == 404


def test_generate_and_latest_with_version_increment(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")

    first = client.post(f"/passports/{ctx.siti_id}")
    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert first.json()["snapshot"]["risk"]["level"] == "none"

    second = client.post(f"/passports/{ctx.siti_id}")
    assert second.status_code == 201
    assert second.json()["version"] == 2

    latest = client.get(f"/passports/{ctx.siti_id}/latest")
    assert latest.status_code == 200
    assert latest.json()["version"] == 2


def test_latest_404_when_not_generated(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.get(f"/passports/{ctx.doni_id}/latest").status_code == 404


def test_generate_risk_student_flags(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(f"/passports/{ctx.doni_id}")
    assert resp.status_code == 201
    flags = resp.json()["snapshot"]["risk"]["flags"]
    # 出席率とスコア下降は実クロックに依存しないので必ず立つ。
    assert "low_attendance" in flags
    assert "score_decline" in flags
    assert resp.json()["snapshot"]["risk"]["level"] == "risk"
