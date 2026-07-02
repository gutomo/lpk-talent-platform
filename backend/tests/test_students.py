from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, Sector, UserRole
from app.services.auth import hash_password

# JSONB を含まない（PortableJSON 化済みの）テーブルのみ SQLite に作成する。
STUDENT_TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
    models.Cohort.__table__,
    models.Enrollment.__table__,
]

PASSWORD = "rahasia123"
LAST_ACTIVE = datetime(2026, 6, 20, 11, 30, tzinfo=UTC)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=STUDENT_TABLES)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        lpk = models.Organization(name="LPK Test", type=OrgType.LPK)
        other = models.Organization(name="LPK Lain", type=OrgType.LPK)
        db.add_all([lpk, other])
        db.flush()

        pw = hash_password(PASSWORD)
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
                               sector=Sector.KAIGO, start_date=date(2026, 4, 1))
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))
        db.add(models.Event(user_id=siti.id, type="pronunciation_attempt", meta={},
                            created_at=LAST_ACTIVE))
        db.add(models.Event(user_id=siti.id, type="login", meta={},
                            created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC)))
        db.commit()
    return factory


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
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
