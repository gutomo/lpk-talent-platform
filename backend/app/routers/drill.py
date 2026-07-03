from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import QuizAttempt, QuizItem, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.drill import AnswerIn, AnswerOut, DailyQuizOut, QuizItemOut
from app.services.drill import build_daily_quiz
from app.services.events import log_event

router = APIRouter(prefix="/drill", tags=["drill"])

Student = Annotated[User, Depends(require_role(UserRole.STUDENT))]


def quiz_item_out(item: QuizItem, is_review: bool = False) -> QuizItemOut:
    return QuizItemOut(
        item_id=item.id,
        section=item.section,
        level=item.level,
        question=item.question,
        choices=item.choices,
        passage_ja=item.meta.get("passage_ja"),
        is_review=is_review,
    )


@router.get("/daily")
def daily_quiz(student: Student, db: DbSession) -> DailyQuizOut:
    """今日の10問（誤答再出題の簡易SRS入り）。同じ日は同じ問題セットを返す。"""
    today = datetime.now(UTC).date()
    items, review_ids = build_daily_quiz(db, student.id, today)
    return DailyQuizOut(
        items=[quiz_item_out(i, is_review=i.id in review_ids) for i in items],
        review_count=len(review_ids),
    )


@router.post("/answers")
def submit_answer(student: Student, db: DbSession, body: AnswerIn) -> AnswerOut:
    """1問の解答を記録し、正誤と解説を返す。"""
    item = db.get(QuizItem, body.item_id)
    # レビュー前（review_flag=True）の問題は存在しない扱いにする（出題対象外）。
    if item is None or item.review_flag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz item not found")
    if body.selected_index >= len(item.choices):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "selected_index out of range")

    is_correct = body.selected_index == item.answer_index
    attempt = QuizAttempt(
        user_id=student.id,
        item_id=item.id,
        selected_index=body.selected_index,
        is_correct=is_correct,
    )
    db.add(attempt)
    log_event(
        db,
        student.id,
        "quiz_answered",
        {"item_id": item.id, "section": item.section, "is_correct": is_correct},
    )
    db.commit()
    return AnswerOut(
        is_correct=is_correct,
        correct_index=item.answer_index,
        explanation_id=item.explanation_id,
    )
