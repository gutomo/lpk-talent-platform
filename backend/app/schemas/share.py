from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ShareLinkOut(BaseModel):
    id: int
    token: str
    passport_version: int
    created_at: datetime
    expires_at: datetime
    revoked: bool
    # 失効も期限切れも False（フロントは active だけ見ればよい）。
    active: bool
    views: int
    last_viewed_at: datetime | None


class SharedPassportOut(BaseModel):
    """未ログインの共有ビューが受け取る全データ。学生情報は snapshot 内に含まれる。"""

    version: int
    created_at: datetime
    expires_at: datetime
    snapshot: dict[str, Any]
