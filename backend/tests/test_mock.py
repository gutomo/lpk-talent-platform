from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.services.drill import MOCK_NUM_QUESTIONS, score_from_correct

# クイズ系のfixture（学生・教師・問題バンク）は test_drill と共通
from tests.test_drill import client, login, session_factory  # noqa: F401

pytestmark = pytest.mark.usefixtures("client")


# ---------------------------------------------------------------------- exam


def test_exam_requires_student_role(client: TestClient) -> None:  # noqa: F811
    assert client.get("/mock/exam").status_code == 401
    login(client, "teacher@example.com")
    assert client.get("/mock/exam").status_code == 403


def test_exam_composition_and_no_answer_leak(client: TestClient) -> None:  # noqa: F811
    login(client)
    body = client.get("/mock/exam").json()
    assert body["num_questions"] == MOCK_NUM_QUESTIONS == 25
    counts = Counter(i["section"] for i in body["items"])
    assert counts == {"grammar": 8, "vocabulary": 8, "reading": 5, "listening": 4}
    for item in body["items"]:
        assert "answer_index" not in item
        if item["section"] == "listening":
            assert item["script_ja"], "stub モードの browser TTS 用に必要"
        else:
            assert item["script_ja"] is None


# -------------------------------------------------------------------- submit


def test_submit_scores_and_persists(client: TestClient, session_factory) -> None:  # noqa: F811
    login(client)
    items = client.get("/mock/exam").json()["items"]
    # 正解は全問 index=1（fixture）。20問正解 + 5問誤答 = 80点。
    answers = [
        {"item_id": item["item_id"], "selected_index": 1 if n < 20 else 0}
        for n, item in enumerate(items)
    ]
    resp = client.post("/mock/submit", json={"answers": answers})
    assert resp.status_code == 201
    body = resp.json()
    assert body["num_questions"] == 25
    assert body["num_correct"] == 20
    assert body["score"] == 80
    assert body["band"] == "N4"
    assert len(body["results"]) == 25
    assert all(r["correct_index"] == 1 for r in body["results"])

    with session_factory() as db:
        mock = db.execute(select(models.MockSession)).scalar_one()
        assert (mock.score, mock.num_questions, mock.num_correct) == (80, 25, 20)
        assert mock.meta["level"] == "N4"
        attempts = db.execute(
            select(models.QuizAttempt).where(models.QuizAttempt.mock_session_id == mock.id)
        ).scalars().all()
        assert len(attempts) == 25
        events = db.execute(
            select(models.Event).where(models.Event.type == "mock_completed")
        ).scalars().all()
        assert len(events) == 1
        assert events[0].meta == {"mock_id": mock.id, "score": 80}


def test_submit_rejects_bad_payloads(client: TestClient, session_factory) -> None:  # noqa: F811
    login(client)
    item_id = client.get("/mock/exam").json()["items"][0]["item_id"]
    with session_factory() as db:
        draft_id = db.execute(
            select(models.QuizItem.id).where(models.QuizItem.review_flag.is_(True))
        ).scalar_one()

    assert client.post("/mock/submit", json={"answers": []}).status_code == 422
    dup = [{"item_id": item_id, "selected_index": 0}] * 2
    assert client.post("/mock/submit", json={"answers": dup}).status_code == 422
    assert (
        client.post("/mock/submit", json={"answers": [{"item_id": draft_id, "selected_index": 0}]})
        .status_code == 404
    )
    assert (
        client.post("/mock/submit", json={"answers": [{"item_id": 99999, "selected_index": 0}]})
        .status_code == 404
    )


def test_score_conversion_rounds() -> None:
    assert score_from_correct(25, 25) == 100
    assert score_from_correct(0, 25) == 0
    assert score_from_correct(17, 25) == 68
    assert score_from_correct(1, 3) == 33


# ------------------------------------------------------------------- history


def test_history_is_ascending(client: TestClient) -> None:  # noqa: F811
    login(client)
    items = client.get("/mock/exam").json()["items"]
    for correct_count in (10, 20):
        answers = [
            {"item_id": item["item_id"], "selected_index": 1 if n < correct_count else 0}
            for n, item in enumerate(items)
        ]
        assert client.post("/mock/submit", json={"answers": answers}).status_code == 201

    history = client.get("/mock/history").json()
    assert [h["score"] for h in history] == [40, 80]
    assert all(h["num_questions"] == 25 for h in history)


# --------------------------------------------------------------------- audio


def test_listening_audio_returns_204_in_stub_mode(
    client: TestClient, session_factory  # noqa: F811
) -> None:
    login(client)
    with session_factory() as db:
        listening_id = db.execute(
            select(models.QuizItem.id).where(models.QuizItem.section == "listening")
        ).scalars().first()
        grammar_id = db.execute(
            select(models.QuizItem.id).where(
                models.QuizItem.section == "grammar", models.QuizItem.review_flag.is_(False)
            )
        ).scalars().first()

    assert client.get(f"/mock/items/{listening_id}/audio").status_code == 204
    assert client.get(f"/mock/items/{grammar_id}/audio").status_code == 404
    assert client.get("/mock/items/99999/audio").status_code == 404
