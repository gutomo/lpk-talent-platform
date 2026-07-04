from datetime import UTC, datetime

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

PASSWORD = "rahasia123"
LAST_ACTIVE = datetime(2026, 6, 20, 11, 30, tzinfo=UTC)
REVIEWED_AT = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)


@pytest.fixture()
def ctx():
    """教師と自組織の学生2名 + 他組織の学生1名。

    siti は低出席・スコア下降・最終利用が古い（3フラグとも立つ）データ持ち。
    budi はデータ無し（利用記録なしの inactive のみ）。
    """
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
        outsider = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                               name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([teacher, admin, siti, budi, outsider])
        db.flush()

        cohort = models.Cohort(org_id=lpk.id, name="2026年4月期 介護コース",
                               sector=Sector.KAIGO, start_date=datetime(2026, 4, 1).date())
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))
        db.add(models.Event(user_id=siti.id, type="pronunciation_attempt", meta={},
                            created_at=LAST_ACTIVE))
        db.add(models.Event(user_id=siti.id, type="login", meta={},
                            created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC)))

        # 発音は上昇（60 → 70 → 80、平均70）。下降フラグは面接側で立てる。
        for k, accuracy in enumerate((60, 70, 80)):
            db.add(models.PronunciationAttempt(
                user_id=siti.id, item_id=1,
                scores={"accuracy": accuracy, "fluency": accuracy, "completeness": accuracy},
                weak_words=[],
                created_at=datetime(2026, 6, 1 + k, 10, 0, tzinfo=UTC),
            ))
        # 出席率70%（80未満 → low_attendance）。
        db.add(models.AttendanceRecord(
            user_id=siti.id, kind=AttendanceKind.MONTHLY,
            record_date=datetime(2026, 5, 1).date(), value=70,
        ))
        # 面接3回：70 → 65 → 50（初期1/3=70、直近1/3=50 → score_decline）。
        sessions = []
        for k, total in enumerate((70, 65, 50)):
            session = models.InterviewSession(
                user_id=siti.id, scenario="self_intro_basic", sector=Sector.KAIGO,
                mode=SessionMode.TEXT, status=SessionStatus.COMPLETED,
                created_at=datetime(2026, 6, 2 + k, 11, 0, tzinfo=UTC),
            )
            db.add(session)
            db.flush()
            for seq, (role, text_ja) in enumerate(
                [(TurnRole.INTERVIEWER, "自己紹介をお願いします。"),
                 (TurnRole.CANDIDATE, "はじめまして。よろしくお願いいたします。")],
                start=1,
            ):
                db.add(models.InterviewTurn(
                    session_id=session.id, seq=seq, role=role, text_ja=text_ja, stt=None,
                ))
            db.add(models.InterviewEvaluation(
                session_id=session.id, rubric_version="test-v1",
                scores={"japanese": total}, total=total,
                feedback={"id": "Bagus.", "ja": "良い回答です。"},
                created_at=datetime(2026, 6, 2 + k, 11, 30, tzinfo=UTC),
                # 最初の1件だけ確認済みにして reviewed_at の直列化を検証する。
                reviewed_at=REVIEWED_AT if k == 0 else None,
                reviewer_id=teacher.id if k == 0 else None,
            ))
            sessions.append(session.id)
        db.commit()

        ctx = {
            "factory": factory,
            "siti_id": siti.id,
            "budi_id": budi.id,
            "outsider_id": outsider.id,
            "session_ids": sessions,  # 古い順
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


def test_students_requires_auth(client: TestClient) -> None:
    assert client.get("/students").status_code == 401


def test_students_rejects_student_role(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert client.get("/students").status_code == 403


def test_students_as_teacher_lists_own_org_only(client: TestClient) -> None:
    login(client, "teacher@example.com")
    resp = client.get("/students")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["name"] for s in body] == ["Budi Santoso", "Siti Rahma"]
    assert all(s["email"] != "dewi@example.com" for s in body)


def test_students_includes_cohort_and_last_active(client: TestClient) -> None:
    login(client, "teacher@example.com")
    body = client.get("/students").json()
    siti = next(s for s in body if s["email"] == "siti@example.com")
    budi = next(s for s in body if s["email"] == "budi@example.com")
    assert siti["cohort_name"] == "2026年4月期 介護コース"
    assert siti["last_active_at"] is not None
    assert siti["last_active_at"].startswith("2026-06-20")
    assert budi["cohort_name"] is None
    assert budi["last_active_at"] is None


def test_students_as_admin(client: TestClient) -> None:
    login(client, "admin@example.com")
    resp = client.get("/students")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_students_progress_fields(client: TestClient) -> None:
    login(client, "teacher@example.com")
    body = client.get("/students").json()
    siti = next(s for s in body if s["email"] == "siti@example.com")
    assert siti["attendance_rate"] == 70
    assert siti["interview_sessions"] == 3
    assert siti["interview_latest_total"] == 50
    assert siti["pron_avg_accuracy"] == 70


def test_students_risk_flags(client: TestClient) -> None:
    login(client, "teacher@example.com")
    body = client.get("/students").json()
    siti = next(s for s in body if s["email"] == "siti@example.com")
    budi = next(s for s in body if s["email"] == "budi@example.com")
    # siti：低出席 + スコア下降 + 最終利用が7日以上前（固定日付なので常に成立）。
    assert siti["risk_level"] == "risk"
    assert siti["risk_flags"] == ["low_attendance", "score_decline", "inactive"]
    # budi：データ無し → 利用記録なしの inactive のみ。進捗はゼロ / null。
    assert budi["risk_level"] == "risk"
    assert budi["risk_flags"] == ["inactive"]
    assert budi["attendance_rate"] is None
    assert budi["interview_sessions"] == 0
    assert budi["interview_latest_total"] is None
    assert budi["pron_avg_accuracy"] is None


# ------------------------------------------------------------ 面接履歴・文字起こし

def test_interviews_requires_staff(client: TestClient, ctx) -> None:
    assert client.get(f"/students/{ctx['siti_id']}/interviews").status_code == 401
    login(client, "siti@example.com")
    assert client.get(f"/students/{ctx['siti_id']}/interviews").status_code == 403


def test_interviews_newest_first_with_reviewed(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.get(f"/students/{ctx['siti_id']}/interviews")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["session_id"] for item in body] == list(reversed(ctx["session_ids"]))
    assert [item["total"] for item in body] == [50, 65, 70]
    # 確認済みなのは最初（最古）の1件だけ。
    assert body[2]["reviewed_at"] is not None
    assert body[0]["reviewed_at"] is None
    # seed の旧シナリオキーは定義に無いので title_ja は None。
    assert body[0]["scenario"] == "self_intro_basic"
    assert body[0]["title_ja"] is None


def test_interviews_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.get(f"/students/{ctx['outsider_id']}/interviews").status_code == 404


def test_transcript_returns_turns_and_evaluation(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    session_id = ctx["session_ids"][0]
    resp = client.get(f"/students/{ctx['siti_id']}/interviews/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["student_id"] == ctx["siti_id"]
    assert body["student_name"] == "Siti Rahma"
    assert body["evaluation"]["evaluation_id"] > 0
    assert [t["role"] for t in body["turns"]] == ["interviewer", "candidate"]
    assert body["turns"][0]["text_ja"] == "自己紹介をお願いします。"
    assert body["evaluation"]["total"] == 70
    assert body["evaluation"]["summary_ja"] == "良い回答です。"
    assert body["evaluation"]["reviewed_at"] is not None
    assert body["evaluation"]["reviewer_name"] == "田中 美咲"


def test_transcript_session_of_other_student_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    # 同組織でも学生とセッションの組が合わなければ404。
    session_id = ctx["session_ids"][0]
    resp = client.get(f"/students/{ctx['budi_id']}/interviews/{session_id}")
    assert resp.status_code == 404


def test_transcript_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    session_id = ctx["session_ids"][0]
    resp = client.get(f"/students/{ctx['outsider_id']}/interviews/{session_id}")
    assert resp.status_code == 404
