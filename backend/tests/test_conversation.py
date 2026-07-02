from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, Sector, UserRole
from app.prompts.conversation_v1 import SCENARIOS
from app.services.auth import hash_password
from app.services.conversation import (
    LlmProviderError,
    generate_reply,
    parse_converse_response,
)

TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
    models.Cohort.__table__,
    models.Enrollment.__table__,
    models.ConversationSession.__table__,
    models.ConversationTurn.__table__,
]

PASSWORD = "rahasia123"


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
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        budi = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Budi Santoso", email="budi@example.com", password_hash=pw)
        db.add_all([
            siti,
            budi,
            models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                        name="田中 美咲", email="teacher@example.com", password_hash=pw),
        ])
        cohort = models.Cohort(org_id=lpk.id, name="介護1期", sector=Sector.KAIGO,
                               start_date=date(2026, 4, 1))
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))
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


# ------------------------------------------------------------------ scenarios


def test_scenarios_requires_student_role(client: TestClient) -> None:
    assert client.get("/conversation/scenarios").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/conversation/scenarios").status_code == 403


def test_scenarios_lists_three(client: TestClient) -> None:
    login(client, "siti@example.com")
    body = client.get("/conversation/scenarios").json()
    assert [s["key"] for s in body] == ["self_intro", "workplace_talk", "hourensou"]
    for s in body:
        assert s["title_ja"] and s["title_id"] and s["description_id"]
        assert s["max_student_turns"] >= 3


# ------------------------------------------------------------------- sessions


def test_create_session_unknown_scenario(client: TestClient) -> None:
    login(client, "siti@example.com")
    resp = client.post("/conversation/sessions", json={"scenario": "nope"})
    assert resp.status_code == 404


def test_create_session_returns_opening_turn(client: TestClient, session_factory) -> None:
    login(client, "siti@example.com")
    resp = client.post("/conversation/sessions", json={"scenario": "self_intro"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenario"] == "self_intro"
    assert body["status"] == "in_progress"
    assert body["done"] is False
    assert len(body["turns"]) == 1
    opening = body["turns"][0]
    assert opening["role"] == "partner"
    assert opening["seq"] == 1
    assert opening["text_ja"].startswith("はじめまして")
    assert opening["furigana"]
    assert opening["hint_id"]

    with session_factory() as db:
        session = db.get(models.ConversationSession, body["session_id"])
        assert session.sector == Sector.KAIGO, "所属コースの職種を引き継ぐ"
        events = db.execute(
            select(models.Event).where(models.Event.type == "conversation_started")
        ).scalars().all()
        assert len(events) == 1
        assert events[0].meta["scenario"] == "self_intro"


def test_full_stub_conversation_completes(client: TestClient, session_factory) -> None:
    login(client, "siti@example.com")
    body = client.post("/conversation/sessions", json={"scenario": "hourensou"}).json()
    sid = body["session_id"]
    max_turns = body["max_student_turns"]

    for n in range(1, max_turns + 1):
        resp = client.post(
            f"/conversation/sessions/{sid}/reply",
            json={"text_ja": f"すみません、報告があります。（{n}回目）"},
        )
        assert resp.status_code == 200
        reply = resp.json()
        assert reply["student_turn"]["role"] == "student"
        assert reply["partner_turn"]["role"] == "partner"
        assert reply["partner_turn"]["text_ja"]
        assert reply["partner_turn"]["furigana"]
        assert reply["partner_turn"]["hint_id"]
        assert reply["done"] is (n == max_turns), "上限到達で done"

    with session_factory() as db:
        session = db.get(models.ConversationSession, sid)
        assert session.status.value == "completed"
        turns = db.execute(
            select(models.ConversationTurn)
            .where(models.ConversationTurn.session_id == sid)
            .order_by(models.ConversationTurn.seq)
        ).scalars().all()
        assert len(turns) == 1 + max_turns * 2, "開幕1 + (学生+AI)×上限"
        assert [t.seq for t in turns] == list(range(1, len(turns) + 1))
        completed = db.execute(
            select(models.Event).where(models.Event.type == "conversation_completed")
        ).scalars().all()
        assert len(completed) == 1
        assert completed[0].meta["student_turns"] == max_turns

    # 完了後の追加発話は 409
    resp = client.post(f"/conversation/sessions/{sid}/reply", json={"text_ja": "もう一度"})
    assert resp.status_code == 409


def test_reply_rejects_other_users_session(client: TestClient) -> None:
    login(client, "siti@example.com")
    sid = client.post("/conversation/sessions", json={"scenario": "self_intro"}).json()[
        "session_id"
    ]
    login(client, "budi@example.com")
    resp = client.post(f"/conversation/sessions/{sid}/reply", json={"text_ja": "こんにちは"})
    assert resp.status_code == 404


def test_reply_validates_text(client: TestClient) -> None:
    login(client, "siti@example.com")
    sid = client.post("/conversation/sessions", json={"scenario": "self_intro"}).json()[
        "session_id"
    ]
    assert (
        client.post(f"/conversation/sessions/{sid}/reply", json={"text_ja": ""}).status_code
        == 422
    )


# ----------------------------------------------------------- service (stub / bedrock)


def test_generate_reply_stub_forces_done_at_cap() -> None:
    scenario = SCENARIOS["self_intro"]
    cap = scenario["max_student_turns"]
    before = generate_reply("self_intro", [], cap - 1)
    assert before["done"] is False
    last = generate_reply("self_intro", [], cap)
    assert last["done"] is True
    assert last["reply_ja"] == scenario["stub_replies"][-1]["text_ja"]


def test_parse_converse_response_extracts_tool_input() -> None:
    resp = {
        "output": {
            "message": {
                "content": [
                    {"text": "前置き"},
                    {
                        "toolUse": {
                            "name": "reply",
                            "input": {
                                "reply_ja": "いいですね。",
                                "reply_furigana": "いいですね。",
                                "hint_id": "Jawab dengan singkat.",
                                "done": False,
                            },
                        }
                    },
                ]
            }
        }
    }
    parsed = parse_converse_response(resp)
    assert parsed["reply_ja"] == "いいですね。"
    assert parsed["done"] is False


def test_parse_converse_response_rejects_bad_payload() -> None:
    with pytest.raises(LlmProviderError):
        parse_converse_response({"output": {"message": {"content": []}}})
    with pytest.raises(LlmProviderError):
        parse_converse_response(
            {
                "output": {
                    "message": {
                        "content": [
                            {"toolUse": {"name": "reply", "input": {"reply_ja": "欠落あり"}}}
                        ]
                    }
                }
            }
        )
