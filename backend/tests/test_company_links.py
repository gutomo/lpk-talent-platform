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
    """LPK（admin / teacher / 学生2名 + Passport未発行の学生1名）と他組織（admin / 学生1名）。

    snapshot の網羅検証は test_passport 側。ここでは組織単位リンクの
    発行・一覧・失効・候補者比較テーブル・個別閲覧・閲覧ログを検証する。
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

        admin = models.User(org_id=lpk.id, role=UserRole.ADMIN, locale=Locale.JA,
                            name="佐藤 健", email="admin@example.com", password_hash=pw)
        teacher = models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                              name="田中 美咲", email="teacher@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        budi = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Budi Santoso", email="budi@example.com", password_hash=pw)
        no_passport = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                                  name="Ayu Baru", email="ayu@example.com", password_hash=pw)
        other_admin = models.User(org_id=other.id, role=UserRole.ADMIN, locale=Locale.JA,
                                  name="鈴木 一郎", email="admin2@example.com", password_hash=pw)
        dewi = models.User(org_id=other.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Dewi Lain", email="dewi@example.com", password_hash=pw)
        db.add_all([admin, teacher, siti, budi, no_passport, other_admin, dewi])
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
            siti_id=siti.id, budi_id=budi.id, no_passport_id=no_passport.id,
            dewi_id=dewi.id,
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


def create_company_link(client: TestClient) -> dict:
    """admin でログインしてリンクを発行し、未ログイン状態に戻す。"""
    login(client, "admin@example.com")
    resp = client.post("/company-links")
    assert resp.status_code == 201
    client.post("/auth/logout")
    return resp.json()


def create_passports(client: TestClient, ctx) -> None:
    """LPK の学生2名（siti / budi）と他組織の dewi に Passport を発行する。"""
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201
    assert client.post(f"/passports/{ctx.budi_id}").status_code == 201
    login(client, "admin2@example.com")
    assert client.post(f"/passports/{ctx.dewi_id}").status_code == 201
    client.post("/auth/logout")


# ------------------------------------------------------------------ 発行

def test_create_requires_auth(client: TestClient) -> None:
    assert client.post("/company-links").status_code == 401


def test_create_rejects_non_admin(client: TestClient) -> None:
    login(client, "teacher@example.com")
    assert client.post("/company-links").status_code == 403
    login(client, "siti@example.com")
    assert client.post("/company-links").status_code == 403


def test_create_token_and_expiry(client: TestClient, ctx) -> None:
    link = create_company_link(client)

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
    assert link["last_viewed_at"] is None


def test_tokens_are_unique_per_link(client: TestClient) -> None:
    login(client, "admin@example.com")
    first = client.post("/company-links").json()
    second = client.post("/company-links").json()
    assert first["token"] != second["token"]


# ------------------------------------------------------------------ 一覧

def test_list_requires_admin(client: TestClient) -> None:
    assert client.get("/company-links").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/company-links").status_code == 403


def test_list_newest_first_own_org_only(client: TestClient) -> None:
    login(client, "admin@example.com")
    first = client.post("/company-links").json()
    second = client.post("/company-links").json()
    # 他組織の admin が発行したリンクは混ざらない。
    login(client, "admin2@example.com")
    client.post("/company-links")

    login(client, "admin@example.com")
    links = client.get("/company-links").json()
    assert [link["id"] for link in links] == [second["id"], first["id"]]


# ------------------------------------------------------------------ 候補者比較テーブル（公開）

def test_candidates_without_login(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    link = create_company_link(client)

    resp = client.get(f"/share/company/{link['token']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lpk_name"] == "LPK Test"

    # 自組織で Passport 発行済みの学生のみ、名前順。dewi（他組織）と ayu（未発行）は出ない。
    names = [c["name"] for c in body["candidates"]]
    assert names == ["Budi Santoso", "Siti Rahma"]

    siti = body["candidates"][1]
    assert siti["student_id"] == ctx.siti_id
    assert siti["passport_version"] == 1
    assert siti["cohort"] == "2026年4月期 介護コース"
    assert siti["sector"] == "kaigo"
    assert siti["pron_avg_accuracy"] == 80
    assert siti["attendance_rate"] == 90
    assert siti["checklist_total"] == 4
    # リスクフラグは企業ビューに出さない。
    assert "risk" not in siti
    assert "risk_level" not in siti


def test_candidates_use_latest_passport_version(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201  # version 2
    link = create_company_link(client)

    body = client.get(f"/share/company/{link['token']}").json()
    by_name = {c["name"]: c for c in body["candidates"]}
    assert len(body["candidates"]) == 2  # 版が増えても1学生1行
    assert by_name["Siti Rahma"]["passport_version"] == 2
    assert by_name["Budi Santoso"]["passport_version"] == 1


def test_candidates_unknown_token_404(client: TestClient) -> None:
    assert client.get(f"/share/company/{'0' * 64}").status_code == 404


def test_candidates_expired_404(client: TestClient, ctx) -> None:
    link = create_company_link(client)

    with ctx.factory() as db:
        row = db.execute(
            select(models.CompanyShareLink)
            .where(models.CompanyShareLink.token == link["token"])
        ).scalar_one()
        row.expires_at = ctx.now - timedelta(days=1)
        db.commit()

    assert client.get(f"/share/company/{link['token']}").status_code == 404

    login(client, "admin@example.com")
    links = client.get("/company-links").json()
    assert links[0]["active"] is False
    assert links[0]["revoked"] is False  # 期限切れは失効とは別状態


# ------------------------------------------------------------------ 個別 Passport（公開）

def test_candidate_detail_without_login(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    link = create_company_link(client)

    resp = client.get(f"/share/company/{link['token']}/students/{ctx.siti_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["snapshot"]["student"]["name"] == "Siti Rahma"
    # リスクフラグは企業ビューに出さない。
    assert "risk" not in body["snapshot"]


def test_candidate_detail_returns_latest_version(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    login(client, "teacher@example.com")
    assert client.post(f"/passports/{ctx.siti_id}").status_code == 201  # version 2
    link = create_company_link(client)

    body = client.get(f"/share/company/{link['token']}/students/{ctx.siti_id}").json()
    assert body["version"] == 2


def test_candidate_detail_404s(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    link = create_company_link(client)

    # 他組織の学生・Passport 未発行・不存在はすべて 404（区別しない）。
    for student_id in (ctx.dewi_id, ctx.no_passport_id, 99999):
        resp = client.get(f"/share/company/{link['token']}/students/{student_id}")
        assert resp.status_code == 404


# ------------------------------------------------------------------ 失効

def test_revoke_blocks_public_views(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    link = create_company_link(client)

    login(client, "admin@example.com")
    resp = client.post(f"/company-links/{link['id']}/revoke")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True
    assert resp.json()["active"] is False

    client.post("/auth/logout")
    assert client.get(f"/share/company/{link['token']}").status_code == 404
    assert (
        client.get(f"/share/company/{link['token']}/students/{ctx.siti_id}").status_code
        == 404
    )
    assert (
        client.get(f"/share/company/{link['token']}/students/{ctx.siti_id}/pdf").status_code
        == 404
    )


def test_revoke_is_idempotent(client: TestClient) -> None:
    link = create_company_link(client)
    login(client, "admin@example.com")
    assert client.post(f"/company-links/{link['id']}/revoke").status_code == 200
    resp = client.post(f"/company-links/{link['id']}/revoke")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_revoke_cross_org_404(client: TestClient) -> None:
    link = create_company_link(client)
    login(client, "admin2@example.com")
    assert client.post(f"/company-links/{link['id']}/revoke").status_code == 404


# ------------------------------------------------------------------ 閲覧ログ

def test_views_are_logged(client: TestClient, ctx) -> None:
    create_passports(client, ctx)
    link = create_company_link(client)

    client.get(f"/share/company/{link['token']}")
    client.get(f"/share/company/{link['token']}")
    client.get(f"/share/company/{link['token']}/students/{ctx.siti_id}")

    login(client, "admin@example.com")
    links = client.get("/company-links").json()
    assert links[0]["views"] == 3
    assert links[0]["last_viewed_at"] is not None

    with ctx.factory() as db:
        row = db.execute(
            select(models.CompanyShareLink)
            .where(models.CompanyShareLink.token == link["token"])
        ).scalar_one()
        assert [e["kind"] for e in row.view_log] == ["candidates", "candidates", "view"]
        # 個別閲覧は「誰を見たか」を残す。
        assert row.view_log[-1]["student_id"] == ctx.siti_id
