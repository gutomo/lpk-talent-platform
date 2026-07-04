"""経営者KPI（/dashboard/kpi）の検証。

集計定義は BUILD_PLAN の KPI 表と同一（services/dashboard.admin_kpi）。
admin 専用で、自組織の学生のみを対象にする。
"""

from datetime import UTC, datetime, timedelta

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
    UserRole,
)
from app.services.auth import hash_password

PASSWORD = "rahasia123"


def _add_evaluation(db, user_id: int, total: int, created_at: datetime,
                    reviewed_at: datetime | None = None) -> None:
    session = models.InterviewSession(
        user_id=user_id, scenario="kaigo", sector=Sector.KAIGO,
        mode=SessionMode.TEXT, status=SessionStatus.COMPLETED,
        created_at=created_at,
    )
    db.add(session)
    db.flush()
    db.add(models.InterviewEvaluation(
        session_id=session.id, rubric_version="test-v1",
        scores={"japanese": total}, total=total,
        feedback={"id": "Bagus.", "ja": "良い回答です。"},
        created_at=created_at, reviewed_at=reviewed_at,
    ))


def _add_mock(db, user_id: int, score: int, created_at: datetime) -> None:
    db.add(models.MockSession(
        user_id=user_id, score=score, num_questions=25,
        num_correct=round(score / 4), created_at=created_at,
    ))


def _add_event(db, user_id: int, created_at: datetime) -> None:
    db.add(models.Event(
        user_id=user_id, type="pronunciation_attempt", meta={}, created_at=created_at,
    ))


@pytest.fixture()
def ctx():
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

        admin = models.User(org_id=lpk.id, role=UserRole.ADMIN, locale=Locale.JA,
                            name="Hendra", email="admin@example.com", password_hash=pw)
        teacher = models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                              name="田中 美咲", email="teacher@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        budi = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Budi Santoso", email="budi@example.com", password_hash=pw)
        rina = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Rina Wati", email="rina@example.com", password_hash=pw)
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([admin, teacher, siti, budi, rina, dewi])
        db.flush()

        # siti：好調学生。模試 40→50→70（N4到達）、面接6回 50×3→60×3（+20%）、
        # 直近7日に4日利用、出席率90%。
        for score, days in ((40, 40), (50, 20), (70, 3)):
            _add_mock(db, siti.id, score, now - timedelta(days=days))
        for k, total in enumerate((50, 50, 50, 60, 60)):
            _add_evaluation(db, siti.id, total, now - timedelta(days=30 - k * 5),
                            reviewed_at=now - timedelta(days=29 - k * 5))
        _add_evaluation(db, siti.id, 60, now - timedelta(days=5))  # 未確認で滞留5日
        for days in (1, 2, 3, 4):
            _add_event(db, siti.id, now - timedelta(days=days))
        db.add(models.AttendanceRecord(
            user_id=siti.id, kind=AttendanceKind.MONTHLY,
            record_date=(now - timedelta(days=10)).date(), value=90,
        ))

        # budi：模試1回（40）、直近利用1日のみ、20日前の利用履歴あり。
        _add_mock(db, budi.id, 40, now - timedelta(days=10))
        _add_event(db, budi.id, now - timedelta(days=2))
        _add_event(db, budi.id, now - timedelta(days=20))

        # rina：出席率70% + 未利用 → リスク学生。
        db.add(models.AttendanceRecord(
            user_id=rina.id, kind=AttendanceKind.MONTHLY,
            record_date=(now - timedelta(days=10)).date(), value=70,
        ))

        # 他組織の学生は一切集計に入らない。
        _add_mock(db, dewi.id, 90, now - timedelta(days=3))
        _add_event(db, dewi.id, now - timedelta(days=1))
        _add_evaluation(db, dewi.id, 80, now - timedelta(days=2))
        db.commit()

        ctx = {"factory": factory, "rina_id": rina.id}
    return ctx


@pytest.fixture()
def client(ctx):
    def override_get_db():
        db = ctx["factory"]()
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


# ------------------------------------------------------------------ 認可

def test_kpi_requires_auth(client: TestClient) -> None:
    assert client.get("/dashboard/kpi").status_code == 401


def test_kpi_rejects_student_and_teacher(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert client.get("/dashboard/kpi").status_code == 403
    client.post("/auth/logout")
    login(client, "teacher@example.com")
    assert client.get("/dashboard/kpi").status_code == 403


# ------------------------------------------------------------------ 集計

def test_kpi_aggregates_own_org(client: TestClient, ctx) -> None:
    login(client, "admin@example.com")
    resp = client.get("/dashboard/kpi")
    assert resp.status_code == 200
    body = resp.json()

    assert body["students"] == 3
    # 最新模試スコア：siti 70（N4）と budi 40。N4到達は3人中1人。
    assert body["n4_rate"] == 33
    assert body["mock_avg"] == 55
    assert body["attendance_avg"] == 80  # (90 + 70) / 2

    cards = body["kpi_cards"]
    # 直近7日で3日以上利用したのは siti のみ。
    assert cards["ai_usage_students"] == 1
    assert cards["ai_usage_rate"] == 33
    assert cards["interview_avg_sessions"] == 2.0  # 6回 / 3名
    assert cards["interview_target_met"] == 0
    # 初回3回平均50 vs 直近3回平均60 → +20%。
    assert cards["interview_improvement_pct"] == 20
    # 初期1/3 vs 直近1/3：siti 40→70、budi 40→40。
    assert cards["mock_early_avg"] == 40
    assert cards["mock_recent_avg"] == 55
    assert cards["review_pending"] == 1
    assert cards["review_avg_waiting_days"] == 5.0


def test_kpi_risk_students_and_weekly(client: TestClient, ctx) -> None:
    login(client, "admin@example.com")
    body = client.get("/dashboard/kpi").json()

    assert [s["id"] for s in body["risk_students"]] == [ctx["rina_id"]]
    flags = body["risk_students"][0]["flags"]
    assert "low_attendance" in flags
    assert "inactive" in flags

    weekly = body["weekly"]
    assert len(weekly) == 8
    # 直近週：siti 4件 + budi 1件 = 5イベント、アクティブ2名、模試は siti の70。
    assert weekly[-1]["events"] == 5
    assert weekly[-1]["active_students"] == 2
    assert weekly[-1]["mock_avg"] == 70
    # 40日前の模試（スコア40）は idx 2 の週に入る。
    assert weekly[2]["mock_avg"] == 40
    # 他組織（dewi）のイベント・模試は入らない。
    assert sum(w["events"] for w in weekly) == 6
    assert body["practice_events_7d"] == 5
