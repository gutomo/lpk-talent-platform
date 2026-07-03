from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import AttendanceKind, Locale, OrgType, Sector, UserRole
from app.services.auth import hash_password

PASSWORD = "rahasia123"

CHECKLIST = {
    "hourensou": 80,
    "punctuality": 85,
    "dormitory": 82,
    "manner": 88,
    "teamwork": 80,
}


def _days_ago(now: datetime, k: int) -> datetime:
    return now - timedelta(days=k)


@pytest.fixture()
def ctx():
    """教師 / 管理者と、自組織の学生(siti)・他組織の学生(dewi)を仕込む。

    siti には発音と出席の最小データだけ入れる（summary のライブ集計と
    出席 upsert の動作確認が目的。網羅的な snapshot 検証は test_passport 側）。
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
        admin = models.User(org_id=lpk.id, role=UserRole.ADMIN, locale=Locale.JA,
                            name="Hendra", email="admin@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([teacher, admin, siti, dewi])
        db.flush()

        cohort = models.Cohort(org_id=lpk.id, name="2026年4月期 介護コース",
                               sector=Sector.KAIGO, start_date=_days_ago(now, 90).date())
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))

        db.add(models.PronunciationAttempt(
            user_id=siti.id, item_id=1,
            scores={"accuracy": 80, "fluency": 80, "completeness": 80},
            weak_words=[{"word": "検温", "accuracy": 55}],
            created_at=_days_ago(now, 3),
        ))
        # テストが投稿する 2026-06-01 と衝突しない固定日にする（実クロック非依存）。
        db.add(models.AttendanceRecord(
            user_id=siti.id, kind=AttendanceKind.MONTHLY,
            record_date=date(2026, 4, 1), value=90, note=None,
        ))
        db.add(models.Event(user_id=siti.id, type="login", meta={},
                            created_at=_days_ago(now, 1)))

        db.commit()
        ns = SimpleNamespace(
            factory=factory, now=now,
            teacher_id=teacher.id, siti_id=siti.id, dewi_id=dewi.id,
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


# ------------------------------------------------------------------ アクセス制御

def test_detail_requires_auth(client: TestClient, ctx) -> None:
    assert client.get(f"/students/{ctx.siti_id}").status_code == 401


def test_detail_rejects_student_role(client: TestClient, ctx) -> None:
    login(client, "siti@example.com")
    assert client.get(f"/students/{ctx.siti_id}").status_code == 403


def test_detail_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.get(f"/students/{ctx.dewi_id}").status_code == 404
    assert client.post(
        f"/students/{ctx.dewi_id}/attendance",
        json={"record_date": "2026-06-01", "value": 90},
    ).status_code == 404
    assert client.post(
        f"/students/{ctx.dewi_id}/attitude",
        json={"checklist": CHECKLIST},
    ).status_code == 404


def test_detail_teacher_is_not_a_student(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.get(f"/students/{ctx.teacher_id}").status_code == 404


# ------------------------------------------------------------------------ 詳細

def test_detail_returns_profile_and_live_summary(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.get(f"/students/{ctx.siti_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Siti Rahma"
    assert body["cohort_name"] == "2026年4月期 介護コース"
    assert body["sector"] == "kaigo"
    # Passport 未生成でもライブ集計が入る。
    assert body["latest_passport"] is None
    assert body["summary"]["pronunciation"]["avg_accuracy"] == 80
    assert body["summary"]["attendance"]["rate"] == 90
    assert [r["value"] for r in body["attendance_records"]] == [90]


def test_detail_as_admin(client: TestClient, ctx) -> None:
    login(client, "admin@example.com")
    assert client.get(f"/students/{ctx.siti_id}").status_code == 200


def test_detail_shows_latest_passport_after_generation(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201
    body = client.get(f"/students/{ctx.siti_id}").json()
    assert body["latest_passport"]["version"] == 1
    # 2版目を作ると最新版が返る（version desc の並びを検証）。
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201
    body = client.get(f"/students/{ctx.siti_id}").json()
    assert body["latest_passport"]["version"] == 2


# ------------------------------------------------------------------------ 出席

def test_attendance_create_and_upsert(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    date_ = "2026-06-01"

    first = client.post(
        f"/students/{ctx.siti_id}/attendance",
        json={"kind": "monthly", "record_date": date_, "value": 70, "note": "体調不良で欠席多め"},
    )
    assert first.status_code == 201
    records = first.json()["attendance_records"]
    assert len(records) == 2  # seed分 + 今回

    # 同一日・同一 kind の再入力は上書き（行が増えない）。
    second = client.post(
        f"/students/{ctx.siti_id}/attendance",
        json={"kind": "monthly", "record_date": date_, "value": 96, "note": "訂正"},
    )
    assert second.status_code == 201
    body = second.json()
    records = [r for r in body["attendance_records"] if r["record_date"] == date_]
    assert len(records) == 1
    assert records[0]["value"] == 96
    assert records[0]["note"] == "訂正"
    # 一覧は日付の新しい順（画面はソートせずこの順で表示する）。
    assert [r["record_date"] for r in body["attendance_records"]] == [date_, "2026-04-01"]
    # summary の出席率も更新後の値で再集計される（2026-04 の 90 と 2026-06 の 96 の月平均）。
    assert body["summary"]["attendance"]["rate"] == 93


def test_attendance_low_rate_flags_risk(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(
        f"/students/{ctx.siti_id}/attendance",
        json={"kind": "monthly", "record_date": "2026-06-01", "value": 40},
    )
    # 2026-04 の 90 と 2026-06 の 40 の月平均 65 < 80 で low_attendance が立つ。
    assert resp.json()["summary"]["attendance"]["rate"] == 65
    assert "low_attendance" in resp.json()["summary"]["risk"]["flags"]


def test_attendance_mixed_kinds_normalized_by_month(client: TestClient, ctx) -> None:
    """月次%と日次(0/100)を混ぜても、日次は月内平均に畳んでから全月平均に入る。

    素朴な全行平均だと日次1行が月次%と同じ重みになり、率とリスクフラグが狂う。
    """
    login(client, "teacher@example.com")
    for day, value in [("2026-06-01", 100), ("2026-06-02", 0), ("2026-06-03", 100)]:
        resp = client.post(
            f"/students/{ctx.siti_id}/attendance",
            json={"kind": "daily", "record_date": day, "value": value},
        )
        assert resp.status_code == 201
    # 2026-04 = 90（月次）、2026-06 = 66.67（日次平均）→ 全体 round(78.33) = 78。
    # 全行平均なら round((90+100+0+100)/4) = 73 になるので、月正規化の退行を検出できる。
    assert resp.json()["summary"]["attendance"]["rate"] == 78


def test_attendance_validates_range(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(
        f"/students/{ctx.siti_id}/attendance",
        json={"kind": "monthly", "record_date": "2026-06-01", "value": 101},
    )
    assert resp.status_code == 422


def test_attendance_logs_event_as_staff(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    client.post(
        f"/students/{ctx.siti_id}/attendance",
        json={"kind": "monthly", "record_date": "2026-06-01", "value": 90},
    )
    with ctx.factory() as db:
        event = db.execute(
            select(models.Event).where(models.Event.type == "attendance_recorded")
        ).scalar_one()
        # 学生の最終利用日を汚さないよう、操作した教師の id で記録する。
        assert event.user_id == ctx.teacher_id
        assert event.meta["student_id"] == ctx.siti_id


# ------------------------------------------------------------------------ 態度

def test_attitude_create_appends_history(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")

    first = client.post(
        f"/students/{ctx.siti_id}/attitude",
        json={"checklist": CHECKLIST, "note": "真面目に取り組んでいます。"},
    )
    assert first.status_code == 201
    assert first.json()["summary"]["attitude"]["checklist"] == CHECKLIST
    assert first.json()["summary"]["attitude"]["note"] == "真面目に取り組んでいます。"

    # 2回目は履歴として積まれ、summary は最新を返す。
    updated = {**CHECKLIST, "hourensou": 60}
    second = client.post(
        f"/students/{ctx.siti_id}/attitude",
        json={"checklist": updated},
    )
    assert second.status_code == 201
    assert second.json()["summary"]["attitude"]["checklist"] == updated
    with ctx.factory() as db:
        count = db.execute(
            select(models.AttitudeReview).where(models.AttitudeReview.user_id == ctx.siti_id)
        ).scalars().all()
        assert len(count) == 2
        assert all(r.reviewer_id == ctx.teacher_id for r in count)


def test_attitude_validates_missing_key(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    incomplete = {k: v for k, v in CHECKLIST.items() if k != "teamwork"}
    resp = client.post(
        f"/students/{ctx.siti_id}/attitude",
        json={"checklist": incomplete},
    )
    assert resp.status_code == 422


def test_attitude_validates_range(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    resp = client.post(
        f"/students/{ctx.siti_id}/attitude",
        json={"checklist": {**CHECKLIST, "manner": 120}},
    )
    assert resp.status_code == 422


def test_attitude_logs_event_as_staff(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    client.post(f"/students/{ctx.siti_id}/attitude", json={"checklist": CHECKLIST})
    with ctx.factory() as db:
        event = db.execute(
            select(models.Event).where(models.Event.type == "attitude_recorded")
        ).scalar_one()
        assert event.user_id == ctx.teacher_id
        assert event.meta["student_id"] == ctx.siti_id
