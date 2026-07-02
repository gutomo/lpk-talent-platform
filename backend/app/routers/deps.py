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
