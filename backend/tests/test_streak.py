from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, UserRole
from app.services.auth import hash_password
from app.services.streak import WIB, current_streak

TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
]

PASSWORD = "rahasia123"
TODAY = date(2026, 7, 2)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        lpk = models.Organization(name="LPK Test", type=OrgType.LPK)
        db.add(lpk)
        db.flush()
        db.add(models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com",
                           password_hash=hash_password(PASSWORD)))
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


def add_event_wib(db, user_id: int, day: date, hour: int = 12) -> None:
    """WIB の指定日に発生したイベントを UTC 保存で追加する。"""
    at_wib = datetime.combine(day, datetime.min.time(), tzinfo=WIB) + timedelta(hours=hour)
    db.add(models.Event(user_id=user_id, type="login", meta={},
                        created_at=at_wib.astimezone(UTC)))


def test_streak_counts_consecutive_days(session_factory) -> None:
    with session_factory() as db:
        for offset in (0, 1, 2):
            add_event_wib(db, 1, TODAY - timedelta(days=offset))
        # 途切れる前の古い活動は数えない
        add_event_wib(db, 1, TODAY - timedelta(days=5))
        db.commit()
        assert current_streak(db, 1, today=TODAY) == {"days": 3, "active_today": True}


def test_streak_alive_until_end_of_today(session_factory) -> None:
    with session_factory() as db:
        add_event_wib(db, 1, TODAY - timedelta(days=1))
        add_event_wib(db, 1, TODAY - timedelta(days=2))
        db.commit()
        assert current_streak(db, 1, today=TODAY) == {"days": 2, "active_today": False}


def test_streak_broken_by_gap(session_factory) -> None:
    with session_factory() as db:
        add_event_wib(db, 1, TODAY - timedelta(days=2))
        db.commit()
        assert current_streak(db, 1, today=TODAY) == {"days": 0, "active_today": False}


def test_streak_without_events(session_factory) -> None:
    with session_factory() as db:
        assert current_streak(db, 1, today=TODAY) == {"days": 0, "active_today": False}


def test_streak_uses_wib_date_boundary(session_factory) -> None:
    with session_factory() as db:
        # 前日 18:00 UTC = 当日 01:00 WIB。WIB では「今日」の活動になる。
        db.add(models.Event(
            user_id=1, type="login", meta={},
            created_at=datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
        ))
        db.commit()
        assert current_streak(db, 1, today=TODAY) == {"days": 1, "active_today": True}


def test_me_streak_endpoint(client: TestClient, session_factory) -> None:
    assert client.get("/me/streak").status_code == 401

    resp = client.post("/auth/login", json={"email": "siti@example.com", "password": PASSWORD})
    assert resp.status_code == 200
    body = client.get("/me/streak").json()
    # ログインは login イベントとして記録されるため、直後の streak は必ず 1 以上。
    assert body["days"] >= 1
    assert body["active_today"] is True
