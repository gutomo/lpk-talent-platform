from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.models.enums import UserRole
from app.services import auth as auth_service

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    if token is not None:
        user = auth_service.get_user_by_token(db, token)
        if user is not None:
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return check


def org_student(db: Session, staff: User, student_id: int) -> User:
    """自組織の学生のみ対象にする。他組織・非学生・不在は 404（存在秘匿）。

    教師 / 管理者が特定の学生を操作する全エンドポイントで共有するアクセス制御。
    """
    student = db.get(User, student_id)
    if student is None or student.role != UserRole.STUDENT or student.org_id != staff.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return student
