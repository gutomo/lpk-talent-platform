from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, QuizSection, UserRole
from app.services.auth import hash_password
from app.services.drill import DAILY_QUIZ_SIZE, DAILY_WRONG_CAP, build_daily_quiz

TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
    models.QuizItem.__table__,
    models.QuizAttempt.__table__,
    models.MockSession.__table__,
]

PASSWORD = "rahasia123"
TODAY = date(2026, 7, 3)


def _quiz_item(section: QuizSection, n: int, **kwargs) -> models.QuizItem:
    meta = {}
    if section == QuizSection.READING:
        meta["passage_ja"] = f"本文{n}"
    if section == QuizSection.LISTENING:
        meta["script_ja"] = f"スクリプト{n}"
    return models.QuizItem(
        section=section,
        level="N4",
        question=f"{section.value}の問題{n}",
        choices=["あ", "い", "う", "え"],
        answer_index=1,
        explanation_id=f"Penjelasan {section.value} {n}",
        review_flag=False,
        meta=meta,
        **kwargs,
    )


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
        pw = hash_password(PASSWORD)
        db.add_all([
            models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                        name="Siti Rahma", email="siti@example.com", password_hash=pw),
            models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                        name="田中 美咲", email="teacher@example.com", password_hash=pw),
        ])
        for n in range(12):
            db.add(_quiz_item(QuizSection.GRAMMAR, n))
        for n in range(10):
            db.add(_quiz_item(QuizSection.VOCABULARY, n))
        for n in range(6):
            db.add(_quiz_item(QuizSection.READING, n))
        for n in range(5):
            db.add(_quiz_item(QuizSection.LISTENING, n))
        # レビュー前の下書きは出題も解答も不可
        draft = _quiz_item(QuizSection.GRAMMAR, 99)
        draft.review_flag = True
        db.add(draft)
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


def login(client: TestClient, email: str = "siti@example.com") -> None:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


def _student_id(session_factory) -> int:
    with session_factory() as db:
        return db.execute(
            select(models.User.id).where(models.User.email == "siti@example.com")
        ).scalar_one()


# ---------------------------------------------------------------- daily quiz


def test_daily_requires_student_role(client: TestClient) -> None:
    assert client.get("/drill/daily").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/drill/daily").status_code == 403


def test_daily_returns_ten_items_without_answers(client: TestClient) -> None:
    login(client)
    body = client.get("/drill/daily").json()
    assert len(body["items"]) == DAILY_QUIZ_SIZE
    assert body["review_count"] == 0
    for item in body["items"]:
        assert item["section"] in ("grammar", "vocabulary", "reading")
        assert len(item["choices"]) == 4
        assert "answer_index" not in item
        assert "explanation_id" not in item
        assert item["script_ja"] is None, "聴解はデイリーに出さない"
    reading = [i for i in body["items"] if i["section"] == "reading"]
    for item in reading:
        assert item["passage_ja"]


def test_daily_is_stable_within_same_day(client: TestClient) -> None:
    login(client)
    first = client.get("/drill/daily").json()
    second = client.get("/drill/daily").json()
    assert [i["item_id"] for i in first["items"]] == [i["item_id"] for i in second["items"]]


def test_srs_reserves_slots_for_wrong_answers(session_factory) -> None:
    """誤答した問題が翌日の出題に優先的に混ざる（簡易SRS）。"""
    user_id = _student_id(session_factory)
    with session_factory() as db:
        first, review_ids = build_daily_quiz(db, user_id, TODAY)
        assert review_ids == set()
        # 3問誤答、7問正解として記録
        for i, item in enumerate(first):
            db.add(models.QuizAttempt(
                user_id=user_id, item_id=item.id,
                selected_index=0 if i < 3 else 1, is_correct=i >= 3,
            ))
        db.commit()
        wrong_ids = {item.id for item in first[:3]}

        second, review_ids = build_daily_quiz(db, user_id, TODAY.replace(day=4))
        assert len(second) == DAILY_QUIZ_SIZE
        assert review_ids == wrong_ids, "誤答3問が全て再出題される"


def test_srs_caps_wrong_repeats(session_factory) -> None:
    user_id = _student_id(session_factory)
    with session_factory() as db:
        first, _ = build_daily_quiz(db, user_id, TODAY)
        for item in first:
            db.add(models.QuizAttempt(
                user_id=user_id, item_id=item.id, selected_index=0, is_correct=False,
            ))
        db.commit()

        second, review_ids = build_daily_quiz(db, user_id, TODAY.replace(day=4))
        assert len(second) == DAILY_QUIZ_SIZE
        # 全問誤答でも、優先枠は上限まで。残りは未出題から補充される。
        unseen = [i for i in second if i.id not in {f.id for f in first}]
        assert len(unseen) == DAILY_QUIZ_SIZE - DAILY_WRONG_CAP


# ------------------------------------------------------------------- answers


def test_answer_records_attempt_and_event(client: TestClient, session_factory) -> None:
    login(client)
    item = client.get("/drill/daily").json()["items"][0]

    resp = client.post(
        "/drill/answers", json={"item_id": item["item_id"], "selected_index": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_correct"] is True
    assert body["correct_index"] == 1
    assert body["explanation_id"]

    resp = client.post(
        "/drill/answers", json={"item_id": item["item_id"], "selected_index": 0}
    )
    assert resp.json()["is_correct"] is False

    with session_factory() as db:
        attempts = db.execute(select(models.QuizAttempt)).scalars().all()
        assert [a.is_correct for a in attempts] == [True, False]
        assert all(a.mock_session_id is None for a in attempts)
        events = db.execute(
            select(models.Event).where(models.Event.type == "quiz_answered")
        ).scalars().all()
        assert len(events) == 2
        assert events[0].meta["item_id"] == item["item_id"]


def test_answer_rejects_draft_and_unknown_items(client: TestClient, session_factory) -> None:
    login(client)
    with session_factory() as db:
        draft_id = db.execute(
            select(models.QuizItem.id).where(models.QuizItem.review_flag.is_(True))
        ).scalar_one()
    assert (
        client.post("/drill/answers", json={"item_id": draft_id, "selected_index": 0})
        .status_code == 404
    )
    assert (
        client.post("/drill/answers", json={"item_id": 99999, "selected_index": 0})
        .status_code == 404
    )
    assert (
        client.post("/drill/answers", json={"item_id": draft_id, "selected_index": 9})
        .status_code == 422
    )
