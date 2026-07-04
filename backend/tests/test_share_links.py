from datetime import UTC, datetime, timedelta
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


def _days_ago(now: datetime, k: int) -> datetime:
    return now - timedelta(days=k)


@pytest.fixture()
def ctx():
    """教師と自組織の学生(siti)・他組織の学生(dewi)。siti には最小の学習データを入れる。

    snapshot の網羅検証は test_passport 側。ここでは共有リンクの
    発行・公開閲覧・失効・期限切れ・閲覧ログを検証する。
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
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([teacher, siti, dewi])
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
        db.add(models.AttendanceRecord(
            user_id=siti.id, kind=AttendanceKind.MONTHLY,
            record_date=_days_ago(now, 30).date(), value=90,
        ))
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


def create_link(client: TestClient, student_id: int) -> dict:
    assert client.post(f"/passports/{student_id}").status_code == 201
    resp = client.post(f"/passports/{student_id}/share-links")
    assert resp.status_code == 201
    return resp.json()


# ------------------------------------------------------------------ 発行

def test_create_requires_auth(client: TestClient, ctx) -> None:
    assert client.post(f"/passports/{ctx.siti_id}/share-links").status_code == 401


def test_create_rejects_student_role(client: TestClient, ctx) -> None:
    login(client, "siti@example.com")
    assert client.post(f"/passports/{ctx.siti_id}/share-links").status_code == 403


def test_create_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.dewi_id}/share-links").status_code == 404


def test_create_404_without_passport(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.siti_id}/share-links").status_code == 404


def test_create_token_and_expiry(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)

    # ランダム32byte = hex 64文字。
    assert len(link["token"]) == 64
    int(link["token"], 16)  # hex として妥当

    expires = datetime.fromisoformat(link["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert timedelta(days=29) < expires - ctx.now < timedelta(days=31)

    assert link["active"] is True
    assert link["revoked"] is False
    assert link["views"] == 0
    assert link["passport_version"] == 1


def test_tokens_are_unique_per_link(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    first = create_link(client, ctx.siti_id)
    second = client.post(f"/passports/{ctx.siti_id}/share-links").json()
    assert first["token"] != second["token"]


# ------------------------------------------------------------------ 公開閲覧

def test_shared_view_without_login(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)
    client.post("/auth/logout")

    resp = client.get(f"/share/{link['token']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["snapshot"]["student"]["name"] == "Siti Rahma"
    assert body["snapshot"]["student"]["cohort"] == "2026年4月期 介護コース"
    # リスクフラグは企業ビューに出さない（public_snapshot で落とす）。
    assert "risk" not in body["snapshot"]


def test_shared_view_unknown_token_404(client: TestClient, ctx) -> None:
    assert client.get(f"/share/{'0' * 64}").status_code == 404


def test_shared_view_logs_each_access(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)

    client.get(f"/share/{link['token']}")
    client.get(f"/share/{link['token']}")

    links = client.get(f"/passports/{ctx.siti_id}/share-links").json()
    assert links[0]["views"] == 2
    assert links[0]["last_viewed_at"] is not None

    with ctx.factory() as db:
        row = db.execute(
            select(models.ShareLink).where(models.ShareLink.token == link["token"])
        ).scalar_one()
        assert [e["kind"] for e in row.view_log] == ["view", "view"]


# ------------------------------------------------------------------ 失効・期限切れ

def test_revoke_blocks_shared_view(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)

    resp = client.post(f"/passports/{ctx.siti_id}/share-links/{link['id']}/revoke")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True
    assert resp.json()["active"] is False

    assert client.get(f"/share/{link['token']}").status_code == 404
    assert client.get(f"/share/{link['token']}/pdf").status_code == 404


def test_revoke_cross_org_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)
    # 他組織の学生 ID との組では見つからない扱いにする。
    resp = client.post(f"/passports/{ctx.dewi_id}/share-links/{link['id']}/revoke")
    assert resp.status_code == 404


def test_expired_link_404(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    link = create_link(client, ctx.siti_id)

    with ctx.factory() as db:
        row = db.execute(
            select(models.ShareLink).where(models.ShareLink.token == link["token"])
        ).scalar_one()
        row.expires_at = ctx.now - timedelta(days=1)
        db.commit()

    assert client.get(f"/share/{link['token']}").status_code == 404

    links = client.get(f"/passports/{ctx.siti_id}/share-links").json()
    assert links[0]["active"] is False
    assert links[0]["revoked"] is False  # 期限切れは失効とは別状態


# ------------------------------------------------------------------ 一覧

def test_list_requires_auth(client: TestClient, ctx) -> None:
    assert client.get(f"/passports/{ctx.siti_id}/share-links").status_code == 401


def test_list_newest_first_with_versions(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    create_link(client, ctx.siti_id)  # version 1 のリンク
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201  # version 2
    second = client.post(f"/passports/{ctx.siti_id}/share-links").json()

    links = client.get(f"/passports/{ctx.siti_id}/share-links").json()
    assert len(links) == 2
    assert links[0]["id"] == second["id"]  # 新しい順
    assert links[0]["passport_version"] == 2
    assert links[1]["passport_version"] == 1
