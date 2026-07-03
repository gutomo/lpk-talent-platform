"""模試モード（25問、スコア0〜100換算）。

出題はステートレス：GET /mock/exam で25問を受け取り、クライアントが解き終えたら
POST /mock/submit で全解答をまとめて採点・保存する。聴解の音源は TTS で都度生成する
（stub モードは 204 を返し、フロントが browser TTS で読み上げる。面接の音声と同じ方式）。
"""

import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.models import MockSession, QuizAttempt, QuizItem, User
from app.models.enums import QuizSection, UserRole
from app.routers.deps import DbSession, require_role
from app.routers.drill import quiz_item_out
from app.schemas.drill import (
    MockExamOut,
    MockHistoryItemOut,
    MockQuestionResultOut,
    MockResultOut,
    MockSubmitIn,
)
from app.services.drill import MOCK_NUM_QUESTIONS, build_mock_exam, score_from_correct
from app.services.events import log_event
from app.services.passport import jlpt_band
from app.services.tts import TTS_MEDIA_TYPE, TtsProviderError, synthesize

router = APIRouter(prefix="/mock", tags=["mock"])

Student = Annotated[User, Depends(require_role(UserRole.STUDENT))]


@router.get("/exam")
def get_exam(student: Student, db: DbSession) -> MockExamOut:
    """模試25問（文法8 / 語彙8 / 読解5 / 聴解4）を無作為に組んで返す。"""
    try:
        items = build_mock_exam(db, random.Random())
    except ValueError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    out = []
    for item in items:
        q = quiz_item_out(item)
        if item.section == QuizSection.LISTENING:
            q.script_ja = item.meta.get("script_ja")
        out.append(q)
    return MockExamOut(items=out, num_questions=MOCK_NUM_QUESTIONS)


@router.post("/submit", status_code=status.HTTP_201_CREATED)
def submit(student: Student, db: DbSession, body: MockSubmitIn) -> MockResultOut:
    """全解答をまとめて採点し、mock_sessions と quiz_attempts に保存する。"""
    item_ids = [a.item_id for a in body.answers]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "duplicate item_id")

    items = {
        i.id: i
        for i in db.execute(
            select(QuizItem).where(QuizItem.id.in_(item_ids), QuizItem.review_flag.is_(False))
        ).scalars()
    }
    missing = [i for i in item_ids if i not in items]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Quiz item not found: {missing[0]}")

    results = []
    num_correct = 0
    for answer in body.answers:
        item = items[answer.item_id]
        if answer.selected_index >= len(item.choices):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "selected_index out of range"
            )
        is_correct = answer.selected_index == item.answer_index
        num_correct += is_correct
        results.append(
            MockQuestionResultOut(
                item_id=item.id,
                is_correct=is_correct,
                correct_index=item.answer_index,
                explanation_id=item.explanation_id,
            )
        )

    num_questions = len(body.answers)
    score = score_from_correct(num_correct, num_questions)
    sections = sorted({items[a.item_id].section.value for a in body.answers})
    mock = MockSession(
        user_id=student.id,
        score=score,
        num_questions=num_questions,
        num_correct=num_correct,
        meta={"level": "N4", "sections": sections},
    )
    db.add(mock)
    db.flush()
    for answer, result in zip(body.answers, results, strict=True):
        db.add(
            QuizAttempt(
                user_id=student.id,
                item_id=answer.item_id,
                mock_session_id=mock.id,
                selected_index=answer.selected_index,
                is_correct=result.is_correct,
            )
        )
    log_event(db, student.id, "mock_completed", {"mock_id": mock.id, "score": score})
    db.commit()
    return MockResultOut(
        mock_id=mock.id,
        score=score,
        num_questions=num_questions,
        num_correct=num_correct,
        band=jlpt_band(score),
        results=results,
    )


@router.get("/history")
def history(student: Student, db: DbSession) -> list[MockHistoryItemOut]:
    """模試スコアの履歴（古い順）。学生UIのトレンドチャートの元データ。"""
    rows = db.execute(
        select(MockSession)
        .where(MockSession.user_id == student.id)
        .order_by(MockSession.created_at, MockSession.id)
    ).scalars()
    return [
        MockHistoryItemOut(
            mock_id=m.id,
            score=m.score,
            num_questions=m.num_questions,
            num_correct=m.num_correct,
            created_at=m.created_at,
        )
        for m in rows
    ]


@router.get("/items/{item_id}/audio")
def listening_audio(student: Student, db: DbSession, item_id: int) -> Response:
    """聴解問題の合成音声（MP3）。stub モードでは 204（フロントが browser TTS）。"""
    item = db.get(QuizItem, item_id)
    if item is None or item.review_flag or item.section != QuizSection.LISTENING:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listening item not found")
    script = item.meta.get("script_ja")
    if not script:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listening item has no script")

    try:
        audio = synthesize(script)
    except TtsProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"tts_provider: {exc}") from exc
    if audio is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(content=audio, media_type=TTS_MEDIA_TYPE)
