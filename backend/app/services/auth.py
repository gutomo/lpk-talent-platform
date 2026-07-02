import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, User

SESSION_COOKIE = "lpk_session"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user_id: int, ttl_days: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=_token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
        )
    )
    return token


def get_user_by_token(db: Session, token: str) -> User | None:
    row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
    ).scalar_one_or_none()
    if row is None:
        return None
    expires_at = row.expires_at
    # SQLite（テスト）は naive datetime を返すので UTC として扱う。
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None
    return db.get(User, row.user_id)


def revoke_session(db: Session, token: str) -> None:
    row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
    ).scalar_one_or_none()
    if row is not None:
        db.delete(row)
