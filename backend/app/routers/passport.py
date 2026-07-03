from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.models import Passport, ShareLink, User
from app.models.enums import UserRole
from app.routers.deps import DbSession, org_student, require_role
from app.schemas.passport import PassportOut
from app.schemas.share import ShareLinkOut
from app.services import pdf as pdf_service
from app.services import share as share_service
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


def _latest(db: DbSession, student_id: int) -> Passport | None:
    return db.execute(
        select(Passport)
        .where(Passport.user_id == student_id)
        .order_by(Passport.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _link_out(link: ShareLink, version: int, now: datetime) -> ShareLinkOut:
    log = link.view_log or []
    last = log[-1].get("at") if log else None
    return ShareLinkOut(
        id=link.id,
        token=link.token,
        passport_version=version,
        created_at=link.created_at,
        expires_at=link.expires_at,
        revoked=link.revoked,
        active=share_service.is_active(link, now),
        views=len(log),
        last_viewed_at=datetime.fromisoformat(last) if last else None,
    )


@router.post("/{student_id}", status_code=status.HTTP_201_CREATED)
def generate_passport(staff: Staff, db: DbSession, student_id: int) -> PassportOut:
    """学生の最新 Talent Passport を生成する（snapshot を確定し version を進める）。"""
    student = org_student(db, staff, student_id)
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
    student = org_student(db, staff, student_id)
    passport = _latest(db, student.id)
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passport not generated yet")
    return _out(passport)


@router.get("/{student_id}/pdf")
def passport_pdf(staff: Staff, db: DbSession, student_id: int) -> Response:
    """最新版 Passport の A4 PDF（候補者紹介シート）を返す。"""
    student = org_student(db, staff, student_id)
    passport = _latest(db, student.id)
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passport not generated yet")
    if not pdf_service.is_available():
        # Windows 開発機など WeasyPrint のネイティブ依存が無い環境。コンテナでは発生しない。
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PDF renderer not available")
    content = pdf_service.render_pdf(passport.version, passport.created_at, passport.snapshot)
    log_event(
        db,
        staff.id,
        "passport_pdf_downloaded",
        {"student_id": student.id, "version": passport.version},
    )
    db.commit()
    filename = f"talent-passport-{student.id}-v{passport.version}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{student_id}/share-links", status_code=status.HTTP_201_CREATED)
def create_share_link(staff: Staff, db: DbSession, student_id: int) -> ShareLinkOut:
    """最新版 Passport への共有リンク（有効期限30日）を発行する。"""
    student = org_student(db, staff, student_id)
    passport = _latest(db, student.id)
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passport not generated yet")
    now = datetime.now(UTC)
    link = share_service.create_share_link(db, passport, now)
    db.flush()
    log_event(
        db,
        staff.id,
        "share_link_created",
        {"student_id": student.id, "link_id": link.id, "version": passport.version},
    )
    db.commit()
    db.refresh(link)
    return _link_out(link, passport.version, now)


@router.get("/{student_id}/share-links")
def list_share_links(staff: Staff, db: DbSession, student_id: int) -> list[ShareLinkOut]:
    """学生の全 Passport 版に対する共有リンクを新しい順に返す。"""
    student = org_student(db, staff, student_id)
    now = datetime.now(UTC)
    rows = db.execute(
        select(ShareLink, Passport.version)
        .join(Passport, Passport.id == ShareLink.passport_id)
        .where(Passport.user_id == student.id)
        .order_by(ShareLink.id.desc())
    ).all()
    return [_link_out(link, version, now) for link, version in rows]


@router.post("/{student_id}/share-links/{link_id}/revoke")
def revoke_share_link(
    staff: Staff, db: DbSession, student_id: int, link_id: int
) -> ShareLinkOut:
    """共有リンクを失効させる（冪等。既に失効済みでも 200）。"""
    student = org_student(db, staff, student_id)
    row = db.execute(
        select(ShareLink, Passport.version)
        .join(Passport, Passport.id == ShareLink.passport_id)
        .where(ShareLink.id == link_id, Passport.user_id == student.id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    link, version = row
    link.revoked = True
    log_event(
        db,
        staff.id,
        "share_link_revoked",
        {"student_id": student.id, "link_id": link.id, "version": version},
    )
    db.commit()
    db.refresh(link)
    return _link_out(link, version, datetime.now(UTC))
