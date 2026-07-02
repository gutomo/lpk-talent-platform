from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.models import Cohort, Enrollment, Event, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.students import StudentListItem

router = APIRouter(prefix="/students", tags=["students"])

Staff = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


@router.get("")
def list_students(staff: Staff, db: DbSession) -> list[StudentListItem]:
    """教師 / 管理者向けの学生一覧。自組織の学生のみ返す。"""
    last_event = (
        select(Event.user_id, func.max(Event.created_at).label("last_active_at"))
        .group_by(Event.user_id)
        .subquery()
    )
    rows = db.execute(
        select(User, Cohort.name, last_event.c.last_active_at)
        .outerjoin(Enrollment, Enrollment.user_id == User.id)
        .outerjoin(Cohort, Cohort.id == Enrollment.cohort_id)
        .outerjoin(last_event, last_event.c.user_id == User.id)
        .where(User.role == UserRole.STUDENT, User.org_id == staff.org_id)
        .order_by(User.name)
    ).all()
    return [
        StudentListItem(
            id=user.id,
            name=user.name,
            email=user.email,
            cohort_name=cohort_name,
            last_active_at=last_active_at,
        )
        for user, cohort_name, last_active_at in rows
    ]
