from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.config import get_settings
from app.models import User
from app.routers.deps import CurrentUser, DbSession
from app.schemas.auth import LoginRequest, UserOut
from app.services import auth as auth_service
from app.services.events import log_event

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, response: Response, db: DbSession) -> UserOut:
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or not auth_service.verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    settings = get_settings()
    token = auth_service.create_session(db, user.id, ttl_days=settings.session_ttl_days)
    log_event(db, user.id, "login")
    db.commit()
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    if token is not None:
        auth_service.revoke_session(db, token)
        db.commit()
    response.delete_cookie(auth_service.SESSION_COOKIE)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
