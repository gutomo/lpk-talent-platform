"""企業向け共有ビュー（ログイン不要）。

トークンのみで認可する。不存在・失効・期限切れは区別せず一律 404
（トークンの存在を外部に漏らさない）。閲覧は share_links.view_log に記録する。
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import Passport
from app.routers.deps import DbSession
from app.schemas.share import SharedPassportOut
from app.services import pdf as pdf_service
from app.services import share as share_service

router = APIRouter(prefix="/share", tags=["share"])


def _resolve(db: DbSession, token: str, now: datetime):
    link = share_service.resolve_active(db, token, now)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    return link


def _log(db: DbSession, link, request: Request, now: datetime, kind: str) -> None:
    client_ip = request.client.host if request.client else None
    share_service.log_view(
        link, now, kind=kind, ip=client_ip, ua=request.headers.get("user-agent")
    )
    db.commit()


@router.get("/{token}")
def view_shared_passport(db: DbSession, token: str, request: Request) -> SharedPassportOut:
    now = datetime.now(UTC)
    link = _resolve(db, token, now)
    passport: Passport = link.passport
    _log(db, link, request, now, "view")
    return SharedPassportOut(
        version=passport.version,
        created_at=passport.created_at,
        expires_at=link.expires_at,
        snapshot=passport.snapshot,
    )


@router.get("/{token}/pdf")
def shared_passport_pdf(db: DbSession, token: str, request: Request) -> Response:
    now = datetime.now(UTC)
    link = _resolve(db, token, now)
    if not pdf_service.is_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PDF renderer not available")
    passport: Passport = link.passport
    content = pdf_service.render_pdf(passport.version, passport.created_at, passport.snapshot)
    _log(db, link, request, now, "pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="talent-passport-v{passport.version}.pdf"'
        },
    )
