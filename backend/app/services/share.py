"""Passport 共有リンク（企業向け・ログイン不要閲覧）のサービス。

BUILD_PLAN Phase 4：ランダム32byteトークン、有効期限30日、失効操作、閲覧ログ。
トークンは secrets.token_hex(32)（=64文字hex）。URL から渡ってくる値のみで解決し、
無効（不存在・失効・期限切れ）はすべて None を返して endpoint 側で一律 404 にする
（トークンの存在を外部に漏らさない）。
"""

import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Passport, ShareLink

SHARE_TTL_DAYS = 30
# 閲覧ログの上限。超えたら古い順に落とす（jsonb の肥大防止）。
VIEW_LOG_LIMIT = 500


def _aware(dt: datetime | None, ref: datetime) -> datetime | None:
    """naive（SQLite 由来）なら ref のタイムゾーンを付与する（passport サービスと同じ方針）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ref.tzinfo)
    return dt


def create_share_link(db: Session, passport: Passport, now: datetime) -> ShareLink:
    """有効期限30日の共有リンクを発行する（commit は呼び出し側）。"""
    link = ShareLink(
        passport_id=passport.id,
        token=secrets.token_hex(32),
        expires_at=now + timedelta(days=SHARE_TTL_DAYS),
        revoked=False,
        view_log=[],
    )
    db.add(link)
    return link


def is_active(link: ShareLink, now: datetime) -> bool:
    expires = _aware(link.expires_at, now)
    return not link.revoked and expires is not None and expires > now


def resolve_active(db: Session, token: str, now: datetime) -> ShareLink | None:
    """トークンから有効な共有リンクを引く。不存在・失効・期限切れは区別せず None。"""
    link = db.execute(
        select(ShareLink).where(ShareLink.token == token)
    ).scalar_one_or_none()
    if link is None or not is_active(link, now):
        return None
    return link


def log_view(link: ShareLink, now: datetime, *, kind: str, ip: str | None, ua: str | None) -> None:
    """閲覧ログを1件追記する。jsonb 列の変更検知のためリストは再代入する。"""
    entry: dict[str, Any] = {"at": now.isoformat(), "kind": kind, "ip": ip, "ua": ua}
    link.view_log = [*(link.view_log or []), entry][-VIEW_LOG_LIMIT:]
