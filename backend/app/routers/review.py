"""添削キュー（教師 / 管理者）。

完了した面接評価のうち reviewed_at が NULL のものを「未確認」として古い順に出す。
確認操作は冪等：既確認の評価に complete しても元の reviewed_at / reviewer_id を保つ。
KPI の「添削キュー滞留時間」はここの waiting_days が参考値になる。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.models import InterviewEvaluation, InterviewSession, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.review import QueueItemOut, ReviewCompleteOut
from app.services.events import log_event
from app.services.interview import SCENARIOS
from app.services.passport import ensure_aware

router = APIRouter(prefix="/review", tags=["review"])

Staff = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


def _queue_item(
    evaluation: InterviewEvaluation,
    session: InterviewSession,
    student_name: str,
    now: datetime,
) -> QueueItemOut:
    scenario = SCENARIOS.get(session.scenario)
    created = ensure_aware(evaluation.created_at, now)
    return QueueItemOut(
        evaluation_id=evaluation.id,
        session_id=session.id,
        student_id=session.user_id,
        student_name=student_name,
        scenario=session.scenario,
        title_ja=scenario["title_ja"] if scenario is not None else None,
        mode=session.mode,
        total=evaluation.total,
        created_at=evaluation.created_at,
        waiting_days=max(0, (now - created).days),
    )


@router.get("/queue")
def review_queue(staff: Staff, db: DbSession) -> list[QueueItemOut]:
    """自組織学生の未確認評価を古い順（滞留が長い順）に返す。"""
    now = datetime.now(UTC)
    rows = db.execute(
        select(InterviewEvaluation, InterviewSession, User.name)
        .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            User.org_id == staff.org_id,
            User.role == UserRole.STUDENT,
            InterviewEvaluation.reviewed_at.is_(None),
        )
        .order_by(InterviewEvaluation.created_at, InterviewEvaluation.id)
    ).all()
    return [_queue_item(ev, session, name, now) for ev, session, name in rows]


@router.post("/evaluations/{evaluation_id}/complete")
def complete_review(staff: Staff, db: DbSession, evaluation_id: int) -> ReviewCompleteOut:
    """評価を確認済みにする。org外は存在を漏らさず404。既確認は冪等に200。"""
    row = db.execute(
        select(InterviewEvaluation, InterviewSession)
        .join(InterviewSession, InterviewSession.id == InterviewEvaluation.session_id)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            InterviewEvaluation.id == evaluation_id,
            User.org_id == staff.org_id,
            User.role == UserRole.STUDENT,
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation not found")
    evaluation, session = row
    if evaluation.reviewed_at is None:
        evaluation.reviewed_at = datetime.now(UTC)
        evaluation.reviewer_id = staff.id
        # 教師の操作なので staff.id で記録し、学生の最終利用日を汚さない。
        log_event(
            db,
            staff.id,
            "evaluation_reviewed",
            {
                "evaluation_id": evaluation.id,
                "session_id": session.id,
                "student_id": session.user_id,
            },
        )
        db.commit()
    return ReviewCompleteOut(
        evaluation_id=evaluation.id,
        reviewed_at=evaluation.reviewed_at,
        reviewer_id=evaluation.reviewer_id,
    )
