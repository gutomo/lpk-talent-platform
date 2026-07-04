"""企業向け組織単位共有リンクの発行・一覧・失効（admin = LPK経営者専用）。

公開側（トークン閲覧）は routers/share.py。トークン1本で自組織の
Passport 発行済み学生全員の比較テーブルと各 Passport の閲覧を許可するため、
発行は経営者に限定する（教師の学生別リンクは /passports 側）。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.models import CompanyShareLink, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.share import CompanyShareLinkOut
from app.services import share as share_service
from app.services.events import log_event

router = APIRouter(prefix="/company-links", tags=["company-links"])

Admin = Annotated[User, Depends(require_role(UserRole.ADMIN))]


def _out(link: CompanyShareLink, now: datetime) -> CompanyShareLinkOut:
    log = link.view_log or []
    last = log[-1].get("at") if log else None
    return CompanyShareLinkOut(
        id=link.id,
        token=link.token,
        created_at=link.created_at,
        expires_at=link.expires_at,
        revoked=link.revoked,
        active=share_service.is_active(link, now),
        views=len(log),
        last_viewed_at=datetime.fromisoformat(last) if last else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_company_link(admin: Admin, db: DbSession) -> CompanyShareLinkOut:
    """自組織の企業向け共有リンク（有効期限30日）を発行する。"""
    now = datetime.now(UTC)
    link = share_service.create_company_share_link(db, admin.org_id, now)
    db.flush()
    log_event(db, admin.id, "company_link_created", {"link_id": link.id})
    db.commit()
    db.refresh(link)
    return _out(link, now)


@router.get("")
def list_company_links(admin: Admin, db: DbSession) -> list[CompanyShareLinkOut]:
    """自組織の企業向け共有リンクを新しい順に返す。"""
    now = datetime.now(UTC)
    links = db.execute(
        select(CompanyShareLink)
        .where(CompanyShareLink.org_id == admin.org_id)
        .order_by(CompanyShareLink.id.desc())
    ).scalars().all()
    return [_out(link, now) for link in links]


@router.post("/{link_id}/revoke")
def revoke_company_link(admin: Admin, db: DbSession, link_id: int) -> CompanyShareLinkOut:
    """企業向け共有リンクを失効させる（冪等。既に失効済みでも 200）。他組織のリンクは 404。"""
    link = db.execute(
        select(CompanyShareLink).where(
            CompanyShareLink.id == link_id, CompanyShareLink.org_id == admin.org_id
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company link not found")
    link.revoked = True
    log_event(db, admin.id, "company_link_revoked", {"link_id": link.id})
    db.commit()
    db.refresh(link)
    return _out(link, datetime.now(UTC))
