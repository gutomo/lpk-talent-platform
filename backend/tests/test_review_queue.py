"""添削キュー（/review/queue と /review/evaluations/{id}/complete）の検証。

キュー対象は自組織学生の未確認（reviewed_at IS NULL）面接評価のみ。
確認操作は冪等で、イベントは staff.id で記録される。
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import (
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
                    reviewed_at: datetime | None = None,
                    reviewer_id: int | None = None) -> int:
    session = models.InterviewSession(
        user_id=user_id, scenario="self_intro_basic", sector=Sector.KAIGO,
        mode=SessionMode.TEXT, status=SessionStatus.COMPLETED,
        created_at=created_at,
    )
    db.add(session)
    db.flush()
    evaluation = models.InterviewEvaluation(
        session_id=session.id, rubric_version="test-v1",
        scores={"japanese": total}, total=total,
        feedback={"id": "Bagus.", "ja": "良い回答です。"},
        created_at=created_at + timedelta(minutes=30),
        reviewed_at=reviewed_at, reviewer_id=reviewer_id,
    )
    db.add(evaluation)
    db.flush()
    return evaluation.id


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

        teacher = models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                              name="田中 美咲", email="teacher@example.com", password_hash=pw)
        admin = models.User(org_id=lpk.id, role=UserRole.ADMIN, locale=Locale.JA,
                            name="Hendra", email="admin@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        budi = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Budi Santoso", email="budi@example.com", password_hash=pw)
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([teacher, admin, siti, budi, dewi])
        db.flush()

        # siti：5日前提出（未確認）と10日前提出（確認済み）。budi：2日前提出（未確認）。
        pending_old = _add_evaluation(db, siti.id, 62, now - timedelta(days=5))
        pending_new = _add_evaluation(db, budi.id, 71, now - timedelta(days=2))
        reviewed = _add_evaluation(db, siti.id, 55, now - timedelta(days=10),
                                   reviewed_at=now - timedelta(days=9),
                                   reviewer_id=teacher.id)
        # 他組織の未確認評価はキューに出ない。
        outsider_eval = _add_evaluation(db, dewi.id, 40, now - timedelta(days=8))
        db.commit()

        ctx = {
            "factory": factory,
            "teacher_id": teacher.id,
            "admin_id": admin.id,
            "siti_id": siti.id,
            "pending_old": pending_old,
            "pending_new": pending_new,
            "reviewed": reviewed,
            "outsider_eval": outsider_eval,
        }
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


def _as_utc(value: str) -> datetime:
    """ISO文字列をUTCの aware datetime に正規化する。

    設定直後のレスポンスは aware（...Z）、SQLite から読み戻すと naive になり、
    文字列比較では同一時刻でも一致しないため。
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ------------------------------------------------------------------ キュー

def test_queue_requires_auth(client: TestClient) -> None:
    assert client.get("/review/queue").status_code == 401


def test_queue_rejects_student_role(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert client.get("/review/queue").status_code == 403


def test_queue_oldest_first_own_org_only(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.get("/review/queue")
    assert resp.status_code == 200
    body = resp.json()
    # 確認済みと他組織の評価は出ない。古い順（滞留が長い順）。
    assert [item["evaluation_id"] for item in body] == [
        ctx["pending_old"], ctx["pending_new"]
    ]
    assert body[0]["student_name"] == "Siti Rahma"
    assert body[0]["waiting_days"] == 4  # 提出は5日前だが評価は30分後 → 4日24時間半前
    assert body[1]["waiting_days"] == 1
    assert body[0]["total"] == 62


def test_queue_visible_to_admin(client: TestClient, ctx) -> None:
    login(client, "admin@example.com")
    assert len(client.get("/review/queue").json()) == 2


# ------------------------------------------------------------------ 確認操作

def test_complete_marks_reviewed_and_logs_event(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(f"/review/evaluations/{ctx['pending_old']}/complete")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reviewed_at"] is not None
    assert body["reviewer_id"] == ctx["teacher_id"]

    assert [item["evaluation_id"] for item in client.get("/review/queue").json()] == [
        ctx["pending_new"]
    ]

    with ctx["factory"]() as db:
        event = db.execute(
            select(models.Event).where(models.Event.type == "evaluation_reviewed")
        ).scalar_one()
        # 教師の操作なので staff.id で記録し、学生の最終利用日を汚さない。
        assert event.user_id == ctx["teacher_id"]
        assert event.meta["evaluation_id"] == ctx["pending_old"]
        assert event.meta["student_id"] == ctx["siti_id"]


def test_complete_is_idempotent(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    first = client.post(f"/review/evaluations/{ctx['pending_old']}/complete").json()

    # 別のスタッフが再実行しても最初の確認情報が保たれる。
    client.post("/auth/logout")
    login(client, "admin@example.com")
    second = client.post(f"/review/evaluations/{ctx['pending_old']}/complete")
    assert second.status_code == 200
    assert _as_utc(second.json()["reviewed_at"]) == _as_utc(first["reviewed_at"])
    assert second.json()["reviewer_id"] == ctx["teacher_id"]

    with ctx["factory"]() as db:
        events = db.execute(
            select(models.Event).where(models.Event.type == "evaluation_reviewed")
        ).scalars().all()
        assert len(events) == 1  # 冪等：2回目はイベントを記録しない


def test_complete_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(f"/review/evaluations/{ctx['outsider_eval']}/complete")
    assert resp.status_code == 404


def test_complete_unknown_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.post("/review/evaluations/99999/complete").status_code == 404


def test_complete_rejects_student_role(client: TestClient, ctx) -> None:
    login(client, "siti@example.com")
    resp = client.post(f"/review/evaluations/{ctx['pending_old']}/complete")
    assert resp.status_code == 403
