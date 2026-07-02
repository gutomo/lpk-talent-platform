import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, UserRole
from app.routers.deps import require_role
from app.services.auth import hash_password

# JSONB を含まない（PortableJSON 化済みの）テーブルのみ SQLite に作成する。
AUTH_TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
]

PASSWORD = "rahasia123"


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=AUTH_TABLES)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        org = models.Organization(name="LPK Test", type=OrgType.LPK)
        db.add(org)
        db.flush()
        db.add(
            models.User(
                org_id=org.id,
                role=UserRole.STUDENT,
                locale=Locale.ID,
                name="Siti Rahma",
                email="siti@example.com",
                password_hash=hash_password(PASSWORD),
            )
        )
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


def login(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"email": "siti@example.com", "password": PASSWORD})
    assert resp.status_code == 200


def test_login_returns_user_and_sets_cookie(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"email": "siti@example.com", "password": PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "student"
    assert body["locale"] == "id"
    assert "lpk_session" in resp.cookies
    assert "password_hash" not in body


def test_login_wrong_password_is_401(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"email": "siti@example.com", "password": "salah"})
    assert resp.status_code == 401


def test_login_unknown_email_is_401(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401


def test_me_requires_session(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_after_login(client: TestClient) -> None:
    login(client)
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "siti@example.com"


def test_logout_revokes_session(client: TestClient) -> None:
    login(client)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_login_is_recorded_as_event(client: TestClient, session_factory) -> None:
    login(client)
    with session_factory() as db:
        events = db.execute(select(models.Event)).scalars().all()
    assert len(events) == 1
    assert events[0].type == "login"


def test_require_role_rejects_other_roles() -> None:
    student = models.User(role=UserRole.STUDENT)
    check = require_role(UserRole.TEACHER, UserRole.ADMIN)
    with pytest.raises(HTTPException) as exc:
        check(student)
    assert exc.value.status_code == 403


def test_require_role_accepts_listed_role() -> None:
    teacher = models.User(role=UserRole.TEACHER)
    check = require_role(UserRole.TEACHER, UserRole.ADMIN)
    assert check(teacher) is teacher
