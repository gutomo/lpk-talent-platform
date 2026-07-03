from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AttendanceRecord, Cohort, Enrollment, Event, Passport, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, org_student, require_role
from app.schemas.students import (
    AttendanceIn,
    AttendanceRecordOut,
    AttitudeIn,
    PassportBrief,
    StudentDetail,
    StudentListItem,
)
from app.services.events import log_event
from app.services.passport import build_snapshot
from app.services.records import (
    add_attitude_review,
    list_attendance,
    upsert_attendance,
)

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


def _attendance_out(records: list[AttendanceRecord]) -> list[AttendanceRecordOut]:
    return [
        AttendanceRecordOut(
            id=r.id,
            kind=r.kind,
            record_date=r.record_date,
            value=r.value,
            note=r.note,
        )
        for r in records
    ]


def _latest_passport(db: DbSession, student_id: int) -> PassportBrief | None:
    passport = db.execute(
        select(Passport)
        .where(Passport.user_id == student_id)
        .order_by(Passport.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if passport is None:
        return None
    return PassportBrief(version=passport.version, created_at=passport.created_at)


def _detail(db: DbSession, student: User) -> StudentDetail:
    """詳細ページの1回分のペイロード。summary はライブ集計を都度組み立てる。"""
    summary = build_snapshot(db, student, datetime.now(UTC))
    return StudentDetail(
        id=student.id,
        name=student.name,
        email=student.email,
        cohort_name=summary["student"]["cohort"],
        sector=summary["student"]["sector"],
        summary=summary,
        attendance_records=_attendance_out(list_attendance(db, student.id)),
        latest_passport=_latest_passport(db, student.id),
    )


@router.get("/{student_id}")
def student_detail(staff: Staff, db: DbSession, student_id: int) -> StudentDetail:
    """教師向けの学生詳細。プロフィール + ライブ集計 + 出席記録 + 最新 Passport。"""
    student = org_student(db, staff, student_id)
    return _detail(db, student)


@router.post("/{student_id}/attendance", status_code=status.HTTP_201_CREATED)
def record_attendance(
    staff: Staff, db: DbSession, student_id: int, body: AttendanceIn
) -> StudentDetail:
    """出席記録を追加 / 訂正する。同一日（同 kind）は上書き。更新後の詳細を返す。"""
    student = org_student(db, staff, student_id)

    def apply() -> None:
        upsert_attendance(
            db,
            user_id=student.id,
            kind=body.kind,
            record_date=body.record_date,
            value=body.value,
            note=body.note,
        )
        # 教師の操作なので学生の最終利用日を汚さないよう staff.id で記録する。
        log_event(
            db,
            staff.id,
            "attendance_recorded",
            {"student_id": student.id, "kind": body.kind, "value": body.value},
        )
        db.commit()

    try:
        apply()
    except IntegrityError:
        # 同時送信で同キー行が先にコミットされた場合（SELECT→INSERT の競合）。
        # ロールバック後は SELECT が既存行を見つけるので、上書きとしてやり直す。
        db.rollback()
        apply()
    return _detail(db, student)


@router.post("/{student_id}/attitude", status_code=status.HTTP_201_CREATED)
def record_attitude(
    staff: Staff, db: DbSession, student_id: int, body: AttitudeIn
) -> StudentDetail:
    """生活態度チェックリストを新規レビューとして記録する。更新後の詳細を返す。"""
    student = org_student(db, staff, student_id)
    add_attitude_review(
        db,
        user_id=student.id,
        reviewer_id=staff.id,
        checklist=body.checklist.model_dump(),
        note=body.note,
    )
    log_event(
        db,
        staff.id,
        "attitude_recorded",
        {"student_id": student.id},
    )
    db.commit()
    return _detail(db, student)
