from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.models import Passport, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.passport import PassportOut
from app.services.events import log_event
from app.services.passport import create_passport

router = APIRouter(prefix="/passports", tags=["passports"])

Staff = Annotated[User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))]


def _out(passport: Passport) -> PassportOut:
    return PassportOut(
        passport_id=passport.id,
        user_id=passport.user_id,
        version=passport.version,
        created_at=passport.created_at,
        snapshot=passport.snapshot,
    )


def _org_student(db: DbSession, staff: User, student_id: int) -> User:
    """自組織の学生のみ対象にする。他組織・非学生・不在は 404。"""
    student = db.get(User, student_id)
    if student is None or student.role != UserRole.STUDENT or student.org_id != staff.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return student


@router.post("/{student_id}", status_code=status.HTTP_201_CREATED)
def generate_passport(staff: Staff, db: DbSession, student_id: int) -> PassportOut:
    """学生の最新 Talent Passport を生成する（snapshot を確定し version を進める）。"""
    student = _org_student(db, staff, student_id)
    passport = create_passport(db, student, datetime.now(UTC))
    # 生成は教師の操作なので events は staff.id で記録する（学生の最終利用日を汚さない）。
    log_event(
        db,
        staff.id,
        "passport_generated",
        {"student_id": student.id, "version": passport.version},
    )
    db.commit()
    db.refresh(passport)
    return _out(passport)


@router.get("/{student_id}/latest")
def latest_passport(staff: Staff, db: DbSession, student_id: int) -> PassportOut:
    """学生の最新版 Passport を返す。未生成なら 404。"""
    student = _org_student(db, staff, student_id)
    passport = db.execute(
        select(Passport)
        .where(Passport.user_id == student.id)
        .order_by(Passport.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passport not generated yet")
    return _out(passport)
