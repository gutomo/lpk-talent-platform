import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import Locale, OrgType, Sector, TurnRole, UserRole
from app.prompts.interview_v1 import RUBRIC_AXES, RUBRIC_VERSION, SCENARIOS
from app.services.auth import hash_password
from app.services.interview import (
    LlmProviderError,
    compute_total,
    evaluate_interview,
    generate_question,
    parse_ask_response,
    parse_evaluate_response,
)

TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
    models.InterviewSession.__table__,
    models.InterviewTurn.__table__,
    models.InterviewEvaluation.__table__,
]

PASSWORD = "rahasia123"

POLITE_ANSWERS = [
    "シティと申します。インドネシアから参りました。よろしくお願いいたします。",
    "家族の世話をした経験があり、日本の介護を学びたいからです。",
    "まず理由をやさしく聞きます。そして、すぐに先輩に報告します。",
    "はい、大丈夫です。早く寝るようにしています。",
    "研修はありますか。",
]


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
            models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                        name="Budi Santoso", email="budi@example.com", password_hash=pw),
            models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                        name="田中 美咲", email="teacher@example.com", password_hash=pw),
        ])
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
    assert client.get("/interview/scenarios").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/interview/scenarios").status_code == 403


def test_scenarios_lists_three_in_priority_order(client: TestClient) -> None:
    login(client, "siti@example.com")
    body = client.get("/interview/scenarios").json()
    assert [s["key"] for s in body] == ["kaigo", "food_manufacturing", "restaurant"]
    for s in body:
        assert s["title_ja"] and s["title_id"] and s["description_id"]
        assert s["sector"] == s["key"]
        assert s["max_candidate_turns"] == 5


# ------------------------------------------------------------------- sessions


def test_create_session_unknown_scenario(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert client.post("/interview/sessions", json={"scenario": "nope"}).status_code == 404


def test_create_session_returns_opening_question(client: TestClient, session_factory) -> None:
    login(client, "siti@example.com")
    resp = client.post("/interview/sessions", json={"scenario": "kaigo"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenario"] == "kaigo"
    assert body["status"] == "in_progress"
    assert body["done"] is False
    assert body["evaluation"] is None
    assert len(body["turns"]) == 1
    opening = body["turns"][0]
    assert opening["role"] == "interviewer"
    assert opening["seq"] == 1
    assert "自己紹介" in opening["text_ja"]
    assert opening["furigana"]
    assert opening["hint_id"]

    with session_factory() as db:
        session = db.get(models.InterviewSession, body["session_id"])
        assert session.sector == Sector.KAIGO, "シナリオ定義の職種を保存する"
        events = db.execute(
            select(models.Event).where(models.Event.type == "interview_started")
        ).scalars().all()
        assert len(events) == 1
        assert events[0].meta["scenario"] == "kaigo"


def test_full_stub_interview_completes_with_evaluation(
    client: TestClient, session_factory
) -> None:
    login(client, "siti@example.com")
    body = client.post("/interview/sessions", json={"scenario": "kaigo"}).json()
    sid = body["session_id"]
    max_turns = body["max_candidate_turns"]

    evaluation = None
    for n in range(1, max_turns + 1):
        resp = client.post(
            f"/interview/sessions/{sid}/reply", json={"text_ja": POLITE_ANSWERS[n - 1]}
        )
        assert resp.status_code == 200
        reply = resp.json()
        assert reply["candidate_turn"]["role"] == "candidate"
        assert reply["interviewer_turn"]["role"] == "interviewer"
        assert reply["interviewer_turn"]["text_ja"]
        assert reply["interviewer_turn"]["furigana"]
        assert reply["done"] is (n == max_turns), "上限到達で done"
        if n < max_turns:
            assert reply["evaluation"] is None
        else:
            evaluation = reply["evaluation"]

    assert evaluation is not None, "完走時に評価が返る"
    assert evaluation["rubric_version"] == RUBRIC_VERSION
    assert set(evaluation["scores"]) == set(RUBRIC_AXES)
    assert all(0 <= v <= 100 for v in evaluation["scores"].values())
    assert 0 <= evaluation["total"] <= 100
    assert evaluation["total"] == compute_total(evaluation["scores"])
    assert evaluation["summary_id"]
    assert evaluation["advice_id"]
    assert len(evaluation["model_answers"]) >= 2
    assert all(m["question_ja"] and m["answer_ja"] for m in evaluation["model_answers"])

    with session_factory() as db:
        session = db.get(models.InterviewSession, sid)
        assert session.status.value == "completed"
        turns = db.execute(
            select(models.InterviewTurn)
            .where(models.InterviewTurn.session_id == sid)
            .order_by(models.InterviewTurn.seq)
        ).scalars().all()
        assert len(turns) == 1 + max_turns * 2, "開幕1 + (学生+面接官)×上限"
        assert [t.seq for t in turns] == list(range(1, len(turns) + 1))
        rows = db.execute(
            select(models.InterviewEvaluation)
            .where(models.InterviewEvaluation.session_id == sid)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].rubric_version == RUBRIC_VERSION
        completed = db.execute(
            select(models.Event).where(models.Event.type == "interview_completed")
        ).scalars().all()
        assert len(completed) == 1
        assert completed[0].meta["total"] == evaluation["total"]

    # 完了後の追加回答は 409
    resp = client.post(f"/interview/sessions/{sid}/reply", json={"text_ja": "もう一度"})
    assert resp.status_code == 409

    # 詳細取得で評価とターンが再表示できる
    detail = client.get(f"/interview/sessions/{sid}").json()
    assert detail["done"] is True
    assert len(detail["turns"]) == 1 + max_turns * 2
    assert detail["evaluation"]["total"] == evaluation["total"]


def _complete_interview(client: TestClient, scenario: str) -> dict:
    """stub モードで面接を完走し、返ってきた evaluation を返す。"""
    body = client.post("/interview/sessions", json={"scenario": scenario}).json()
    sid = body["session_id"]
    evaluation = None
    for n in range(body["max_candidate_turns"]):
        reply = client.post(
            f"/interview/sessions/{sid}/reply",
            json={"text_ja": POLITE_ANSWERS[min(n, len(POLITE_ANSWERS) - 1)]},
        ).json()
        evaluation = reply["evaluation"]
    assert evaluation is not None
    return {"session_id": sid, "total": evaluation["total"]}


# --------------------------------------------------------------------- history


def test_history_requires_student_role(client: TestClient) -> None:
    assert client.get("/interview/history").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/interview/history").status_code == 403


def test_history_empty_before_any_interview(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert client.get("/interview/history").json() == []


def test_history_lists_completed_only_newest_first(client: TestClient) -> None:
    login(client, "siti@example.com")
    first = _complete_interview(client, "kaigo")
    second = _complete_interview(client, "restaurant")
    # 未完了セッションは履歴に出さない（評価が無いため）。
    open_sid = client.post("/interview/sessions", json={"scenario": "food_manufacturing"}).json()[
        "session_id"
    ]

    history = client.get("/interview/history").json()
    assert [h["session_id"] for h in history] == [second["session_id"], first["session_id"]]
    assert open_sid not in [h["session_id"] for h in history]

    latest = history[0]
    assert latest["scenario"] == "restaurant"
    assert latest["title_id"] == SCENARIOS["restaurant"]["title_id"]
    assert latest["sector"] == "restaurant"
    assert latest["mode"] == "text"
    assert latest["total"] == second["total"]
    assert latest["created_at"]


def test_history_scoped_to_student(client: TestClient) -> None:
    login(client, "siti@example.com")
    _complete_interview(client, "kaigo")
    login(client, "budi@example.com")
    assert client.get("/interview/history").json() == []


def test_reply_rejects_other_users_session(client: TestClient) -> None:
    login(client, "siti@example.com")
    sid = client.post("/interview/sessions", json={"scenario": "restaurant"}).json()[
        "session_id"
    ]
    login(client, "budi@example.com")
    assert (
        client.post(f"/interview/sessions/{sid}/reply", json={"text_ja": "こんにちは"}).status_code
        == 404
    )
    assert client.get(f"/interview/sessions/{sid}").status_code == 404


def test_reply_validates_text(client: TestClient) -> None:
    login(client, "siti@example.com")
    sid = client.post("/interview/sessions", json={"scenario": "kaigo"}).json()["session_id"]
    assert (
        client.post(f"/interview/sessions/{sid}/reply", json={"text_ja": ""}).status_code == 422
    )


# ----------------------------------------------------------- service (stub / bedrock)


def test_generate_question_stub_forces_done_at_cap() -> None:
    scenario = SCENARIOS["kaigo"]
    cap = scenario["max_candidate_turns"]
    before = generate_question("kaigo", [], cap - 1)
    assert before["done"] is False
    last = generate_question("kaigo", [], cap)
    assert last["done"] is True
    assert last["question_ja"] == scenario["stub_questions"][-1]["text_ja"]


def test_evaluate_stub_rewards_polite_and_hourensou() -> None:
    polite = [(TurnRole.CANDIDATE, a) for a in POLITE_ANSWERS]
    blunt = [(TurnRole.CANDIDATE, a) for a in ["シティ", "うん", "わからない", "はい", "ない"]]
    high = evaluate_interview("kaigo", polite)
    low = evaluate_interview("kaigo", blunt)
    assert high["scores"]["keigo"] > low["scores"]["keigo"]
    assert high["scores"]["hourensou"] > low["scores"]["hourensou"]
    assert high["total"] > low["total"]
    assert evaluate_interview("kaigo", polite) == high, "同一入力で決定的"
    assert high["feedback"]["id"] and high["feedback"]["ja"]
    assert high["feedback"]["model_answers"] == SCENARIOS["kaigo"]["model_answers"]


def _tool_resp(name: str, tool_input: dict) -> dict:
    return {"output": {"message": {"content": [{"toolUse": {"name": name, "input": tool_input}}]}}}


def test_parse_ask_response_extracts_tool_input() -> None:
    parsed = parse_ask_response(
        _tool_resp(
            "ask",
            {
                "question_ja": "どうしてですか。",
                "furigana": "どうしてですか。",
                "hint_id": "Jelaskan alasannya.",
                "done": False,
            },
        )
    )
    assert parsed["question_ja"] == "どうしてですか。"
    assert parsed["done"] is False


def test_parse_ask_response_rejects_bad_payload() -> None:
    with pytest.raises(LlmProviderError):
        parse_ask_response({"output": {"message": {"content": []}}})
    with pytest.raises(LlmProviderError):
        parse_ask_response(_tool_resp("ask", {"question_ja": "欠落あり"}))


def test_parse_evaluate_response_clamps_scores() -> None:
    parsed = parse_evaluate_response(
        _tool_resp(
            "evaluate",
            {
                "scores": {
                    "japanese": 130,
                    "consistency": -10,
                    "keigo": 72,
                    "hourensou": 65,
                    "clarity": 80,
                },
                "summary_id": "Bagus.",
                "summary_ja": "良いです。",
                "advice_id": "Latih keigo.",
                "model_answers": [{"question_ja": "Q", "answer_ja": "A"}],
            },
        )
    )
    assert parsed["scores"]["japanese"] == 100, "上振れは100に丸める"
    assert parsed["scores"]["consistency"] == 0, "下振れは0に丸める"
    assert parsed["feedback"]["model_answers"] == [{"question_ja": "Q", "answer_ja": "A"}]


def test_parse_evaluate_response_rejects_missing_axis() -> None:
    with pytest.raises(LlmProviderError):
        parse_evaluate_response(
            _tool_resp(
                "evaluate",
                {
                    "scores": {"japanese": 70},
                    "summary_id": "s",
                    "summary_ja": "s",
                    "advice_id": "a",
                    "model_answers": [],
                },
            )
        )
    with pytest.raises(LlmProviderError):
        parse_evaluate_response(_tool_resp("evaluate", {"scores": {}}))
