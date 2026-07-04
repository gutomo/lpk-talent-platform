"""Passport 共有リンク（企業向け・ログイン不要閲覧）のサービス。

BUILD_PLAN Phase 4：ランダム32byteトークン、有効期限30日、失効操作、閲覧ログ。
トークンは secrets.token_hex(32)（=64文字hex）。URL から渡ってくる値のみで解決し、
無効（不存在・失効・期限切れ）はすべて None を返して endpoint 側で一律 404 にする
（トークンの存在を外部に漏らさない）。

Phase 5 企業ビュー：CompanyShareLink（組織単位）も同じ semantics で扱う。
トークン1本で、その組織の Passport 発行済み学生全員の比較テーブルと
各 Passport の閲覧を許可する。
"""

import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyShareLink, Passport, ShareLink, User
from app.models.enums import UserRole

SHARE_TTL_DAYS = 30
# 閲覧ログの上限。超えたら古い順に落とす（jsonb の肥大防止）。
VIEW_LOG_LIMIT = 500

# ShareLink と CompanyShareLink は token / expires_at / revoked / view_log が同一構造。
AnyShareLink = ShareLink | CompanyShareLink


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


def is_active(link: AnyShareLink, now: datetime) -> bool:
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


def log_view(
    link: AnyShareLink,
    now: datetime,
    *,
    kind: str,
    ip: str | None,
    ua: str | None,
    student_id: int | None = None,
) -> None:
    """閲覧ログを1件追記する。jsonb 列の変更検知のためリストは再代入する。

    student_id は企業リンク経由の個別 Passport 閲覧で「誰を見たか」を残すための任意項目。
    """
    entry: dict[str, Any] = {"at": now.isoformat(), "kind": kind, "ip": ip, "ua": ua}
    if student_id is not None:
        entry["student_id"] = student_id
    link.view_log = [*(link.view_log or []), entry][-VIEW_LOG_LIMIT:]


def public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """公開（企業向け）レスポンス用の snapshot。リスクフラグは企業ビューに出さない方針。"""
    return {k: v for k, v in snapshot.items() if k != "risk"}


# ------------------------------------------------------------------ 企業向け組織単位リンク


def create_company_share_link(db: Session, org_id: int, now: datetime) -> CompanyShareLink:
    """組織単位の企業向け共有リンク（有効期限30日）を発行する（commit は呼び出し側）。"""
    link = CompanyShareLink(
        org_id=org_id,
        token=secrets.token_hex(32),
        expires_at=now + timedelta(days=SHARE_TTL_DAYS),
        revoked=False,
        view_log=[],
    )
    db.add(link)
    return link


def resolve_active_company(db: Session, token: str, now: datetime) -> CompanyShareLink | None:
    """トークンから有効な企業リンクを引く。不存在・失効・期限切れは区別せず None。"""
    link = db.execute(
        select(CompanyShareLink).where(CompanyShareLink.token == token)
    ).scalar_one_or_none()
    if link is None or not is_active(link, now):
        return None
    return link


def latest_passport_for(db: Session, org_id: int, student_id: int) -> Passport | None:
    """企業リンク経由の個別閲覧用。組織内の学生の最新版 Passport を返す。

    他組織・非学生・Passport 未発行は区別せず None（endpoint 側で一律 404）。
    """
    return db.execute(
        select(Passport)
        .join(User, User.id == Passport.user_id)
        .where(
            Passport.user_id == student_id,
            User.org_id == org_id,
            User.role == UserRole.STUDENT,
        )
        .order_by(Passport.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_passports(db: Session, org_id: int) -> list[tuple[Passport, User]]:
    """組織の学生ごとに最新版 Passport を返す（Passport 未発行の学生は含めない）。"""
    rows = db.execute(
        select(Passport, User)
        .join(User, User.id == Passport.user_id)
        .where(User.org_id == org_id, User.role == UserRole.STUDENT)
        .order_by(Passport.user_id, Passport.version.desc())
    ).all()
    latest: dict[int, tuple[Passport, User]] = {}
    for passport, user in rows:
        latest.setdefault(user.id, (passport, user))
    return sorted(latest.values(), key=lambda pair: pair[1].name)


def candidate_row(passport: Passport, user: User) -> dict[str, Any]:
    """比較テーブルの1行を snapshot から組み立てる。リスクフラグは載せない。"""
    snap = passport.snapshot or {}
    student = snap.get("student") or {}
    level = snap.get("japanese_level") or {}
    pron = snap.get("pronunciation") or {}
    itv = snap.get("interview") or {}
    attendance = snap.get("attendance") or {}
    checklist = snap.get("checklist") or []
    return {
        "student_id": user.id,
        "name": student.get("name", user.name),
        "cohort": student.get("cohort"),
        "sector": student.get("sector"),
        "passport_version": passport.version,
        "generated_at": passport.created_at,
        "level_current": level.get("current"),
        "pron_avg_accuracy": pron.get("avg_accuracy"),
        "interview_sessions": itv.get("sessions", 0),
        "interview_latest_total": itv.get("latest_total"),
        "attendance_rate": attendance.get("rate"),
        "checklist_done": sum(1 for item in checklist if item.get("done")),
        "checklist_total": len(checklist),
    }
