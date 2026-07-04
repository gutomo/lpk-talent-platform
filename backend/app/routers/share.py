"""企業向け共有ビュー（ログイン不要）。

トークンのみで認可する。不存在・失効・期限切れは区別せず一律 404
（トークンの存在を外部に漏らさない）。閲覧は各リンクの view_log に記録する。

- /share/{token}：学生別リンク（ShareLink）。Passport 1件の閲覧。
- /share/company/{token}：組織単位リンク（CompanyShareLink）。候補者比較テーブルと
  各学生の最新版 Passport・PDF の閲覧。
snapshot はどちらも public_snapshot でリスクフラグを落としてから返す
（リスクは教師・経営者向けの内部指標。企業ビューには出さない方針）。
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import Organization, Passport
from app.routers.deps import DbSession
from app.schemas.share import CandidateRow, SharedCandidatesOut, SharedPassportOut
from app.services import pdf as pdf_service
from app.services import share as share_service

router = APIRouter(prefix="/share", tags=["share"])


def _resolve(db: DbSession, token: str, now: datetime):
    link = share_service.resolve_active(db, token, now)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    return link


def _resolve_company(db: DbSession, token: str, now: datetime):
    link = share_service.resolve_active_company(db, token, now)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    return link


def _log(
    db: DbSession,
    link,
    request: Request,
    now: datetime,
    kind: str,
    student_id: int | None = None,
) -> None:
    client_ip = request.client.host if request.client else None
    share_service.log_view(
        link,
        now,
        kind=kind,
        ip=client_ip,
        ua=request.headers.get("user-agent"),
        student_id=student_id,
    )
    db.commit()


def _passport_out(passport: Passport, expires_at: datetime) -> SharedPassportOut:
    return SharedPassportOut(
        version=passport.version,
        created_at=passport.created_at,
        expires_at=expires_at,
        snapshot=share_service.public_snapshot(passport.snapshot),
    )


def _pdf_response(passport: Passport) -> Response:
    if not pdf_service.is_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PDF renderer not available")
    content = pdf_service.render_pdf(
        passport.version, passport.created_at, share_service.public_snapshot(passport.snapshot)
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="talent-passport-v{passport.version}.pdf"'
        },
    )


# ------------------------------------------------------------------ 組織単位リンク（企業ビュー）
# {token} の汎用ルートより先に登録し、/share/company/... が確実にこちらへ落ちるようにする。


@router.get("/company/{token}")
def view_shared_candidates(db: DbSession, token: str, request: Request) -> SharedCandidatesOut:
    """候補者比較テーブル。組織の Passport 発行済み学生全員の最新版snapshot要約。"""
    now = datetime.now(UTC)
    link = _resolve_company(db, token, now)
    org = db.get(Organization, link.org_id)
    rows = share_service.latest_passports(db, link.org_id)
    _log(db, link, request, now, "candidates")
    return SharedCandidatesOut(
        lpk_name=org.name if org is not None else "",
        expires_at=link.expires_at,
        candidates=[
            CandidateRow(**share_service.candidate_row(passport, user))
            for passport, user in rows
        ],
    )


@router.get("/company/{token}/students/{student_id}")
def view_shared_candidate(
    db: DbSession, token: str, student_id: int, request: Request
) -> SharedPassportOut:
    """企業リンク経由の個別 Passport 閲覧（常に最新版）。"""
    now = datetime.now(UTC)
    link = _resolve_company(db, token, now)
    passport = share_service.latest_passport_for(db, link.org_id, student_id)
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    _log(db, link, request, now, "view", student_id=student_id)
    return _passport_out(passport, link.expires_at)


@router.get("/company/{token}/students/{student_id}/pdf")
def shared_candidate_pdf(
    db: DbSession, token: str, student_id: int, request: Request
) -> Response:
    now = datetime.now(UTC)
    link = _resolve_company(db, token, now)
    passport = share_service.latest_passport_for(db, link.org_id, student_id)
    if passport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    response = _pdf_response(passport)
    _log(db, link, request, now, "pdf", student_id=student_id)
    return response


# ------------------------------------------------------------------ 学生別リンク


@router.get("/{token}")
def view_shared_passport(db: DbSession, token: str, request: Request) -> SharedPassportOut:
    now = datetime.now(UTC)
    link = _resolve(db, token, now)
    passport: Passport = link.passport
    _log(db, link, request, now, "view")
    return _passport_out(passport, link.expires_at)


@router.get("/{token}/pdf")
def shared_passport_pdf(db: DbSession, token: str, request: Request) -> Response:
    now = datetime.now(UTC)
    link = _resolve(db, token, now)
    response = _pdf_response(link.passport)
    _log(db, link, request, now, "pdf")
    return response
