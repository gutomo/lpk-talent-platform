"""Passport PDF（WeasyPrint）のテスト。

WeasyPrint は Pango 等のネイティブライブラリが無い環境（Windows 開発機）では
import できないため、実レンダリングのテストは is_available() で skip する。
CI / コンテナ（Linux）では必ず実行される想定。HTML 組み立てとエンドポイントの
認可はどの環境でも検証する。
"""

import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.models.enums import (
    AttendanceKind,
    Locale,
    OrgType,
    Sector,
    SessionMode,
    SessionStatus,
    TurnRole,
    UserRole,
)
from app.services import pdf as pdf_service
from app.services.auth import hash_password

PASSWORD = "rahasia123"

needs_weasyprint = pytest.mark.skipif(
    not pdf_service.is_available(),
    reason="WeasyPrint native libraries not available (run in Linux container)",
)


def _days_ago(now: datetime, k: int) -> datetime:
    return now - timedelta(days=k)


@pytest.fixture()
def ctx():
    """PDF に全セクションが載るよう、siti に一通りのデータを入れる。"""
    now = datetime.now(UTC)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    pw = hash_password(PASSWORD)

    with factory() as db:
        lpk = models.Organization(name="LPK Test", type=OrgType.LPK)
        db.add(lpk)
        db.flush()

        teacher = models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                              name="田中 美咲", email="teacher@example.com", password_hash=pw)
        siti = models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                           name="Siti Rahma", email="siti@example.com", password_hash=pw)
        db.add_all([teacher, siti])
        db.flush()

        cohort = models.Cohort(org_id=lpk.id, name="2026年4月期 介護コース",
                               sector=Sector.KAIGO, start_date=_days_ago(now, 90).date())
        db.add(cohort)
        db.flush()
        db.add(models.Enrollment(cohort_id=cohort.id, user_id=siti.id))

        for ago, acc in [(20, 70), (10, 80), (5, 90)]:
            db.add(models.PronunciationAttempt(
                user_id=siti.id, item_id=1,
                scores={"accuracy": acc, "fluency": acc, "completeness": acc},
                weak_words=[{"word": "検温", "accuracy": 55}],
                created_at=_days_ago(now, ago),
            ))
        sess = models.InterviewSession(
            user_id=siti.id, scenario="kaigo_interview", sector=Sector.KAIGO,
            mode=SessionMode.VOICE, status=SessionStatus.COMPLETED,
            created_at=_days_ago(now, 8),
        )
        db.add(sess)
        db.flush()
        db.add(models.InterviewTurn(session_id=sess.id, seq=1, role=TurnRole.CANDIDATE,
                                    text_ja="はじめまして。よろしくお願いします。", stt=None))
        db.add(models.InterviewEvaluation(
            session_id=sess.id, rubric_version="test-v0",
            scores={"japanese": 70}, feedback={}, total=70,
            created_at=_days_ago(now, 8),
        ))
        db.add(models.MockSession(user_id=siti.id, score=68, num_questions=25,
                                  num_correct=17, meta={}, created_at=_days_ago(now, 10)))
        db.add(models.AttendanceRecord(user_id=siti.id, kind=AttendanceKind.MONTHLY,
                                       record_date=_days_ago(now, 30).date(), value=92))
        db.add(models.AttitudeReview(
            user_id=siti.id, reviewer_id=teacher.id,
            checklist={"hourensou": 80, "punctuality": 85, "dormitory": 82,
                       "manner": 88, "teamwork": 80},
            note="真面目に取り組んでいます。", created_at=_days_ago(now, 20)))
        db.add(models.Event(user_id=siti.id, type="login", meta={},
                            created_at=_days_ago(now, 1)))
        db.commit()
        ns = SimpleNamespace(factory=factory, now=now, siti_id=siti.id)
    return ns


@pytest.fixture()
def client(ctx):
    def override_get_db():
        db = ctx.factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, email: str) -> None:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


def make_passport(client: TestClient, student_id: int) -> dict:
    resp = client.post(f"/passports/{student_id}")
    assert resp.status_code == 201
    return resp.json()


# ------------------------------------------------------------------ HTML 組み立て

def test_render_html_contains_all_sections(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    passport = make_passport(client, ctx.siti_id)

    html = pdf_service.render_html(
        passport["version"], passport["created_at"], passport["snapshot"]
    )
    assert "Siti Rahma" in html
    assert "2026年4月期 介護コース" in html
    assert "職種：介護" in html
    assert "日本語レベル" in html
    assert "検温" in html
    assert "報連相" in html
    assert "はじめまして。よろしくお願いします。" in html
    # 整形漏れ（Python の None がそのまま出る）を検出する。
    assert "None" not in html
    # 内部運用向けのリスクフラグは企業提出用シートに載せない。
    assert "リスク" not in html
    assert "risk" not in html


def test_render_html_minimal_snapshot(ctx) -> None:
    """データが無い学生でも豆腐や None を出さずに描画できる。"""
    minimal = {
        "snapshot_version": "passport-v1",
        "student": {"name": "Budi", "cohort": None, "sector": None},
        "japanese_level": {"current": None, "trend": []},
        "pronunciation": {"attempts": 0, "avg_accuracy": None, "weak_words": []},
        "conversation": {"completed": 0},
        "interview": {"sessions": 0, "latest_total": None, "avg_total": None,
                      "trend": [], "transcript_excerpt": []},
        "attendance": {"rate": None, "records": 0},
        "attitude": None,
        "checklist": [],
        "risk": {"flags": [], "level": "none"},
    }
    html = pdf_service.render_html(1, datetime(2026, 7, 3, tzinfo=UTC), minimal)
    assert "Budi" in html
    assert "計測中" in html
    assert "None" not in html


# ------------------------------------------------------------------ PDF 実レンダリング

@needs_weasyprint
def test_pdf_renders_with_noto_and_no_tofu(client: TestClient, ctx) -> None:
    """豆腐チェック：Noto Sans JP が埋め込まれ、日本語がテキストとして抽出できること。

    グリフ欠け（豆腐）だと ToUnicode の対応が失われ抽出文字列が壊れるため、
    抽出テキストに期待する日本語が含まれることを確認する。
    """
    from pypdf import PdfReader

    login(client, "teacher@example.com")
    passport = make_passport(client, ctx.siti_id)
    content = pdf_service.render_pdf(
        passport["version"], passport["created_at"], passport["snapshot"]
    )

    assert content.startswith(b"%PDF")

    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) <= 2  # A4 1〜2枚の体裁

    # 同梱の Noto Sans JP が実際に埋め込まれていること。
    # Pango がサブセット名を XXXXXX+Noto-Sans-JP 形式にするためハイフンを除いて比較する。
    fonts: set[str] = set()
    for page in reader.pages:
        font_dict = page.get("/Resources", {}).get("/Font", {})
        for ref in font_dict.values():
            fonts.add(str(ref.get_object().get("/BaseFont", "")))
    assert any("NotoSansJP" in name.replace("-", "") for name in fonts), fonts
    text = "".join(page.extract_text() for page in reader.pages)
    assert "Siti Rahma" in text
    assert "候補者紹介シート" in text
    assert "日本語レベル" in text
    assert "介護" in text
    assert "報連相" in text
    assert "�" not in text  # 置換文字（抽出不能グリフ）が無い


@needs_weasyprint
def test_pdf_endpoint_returns_pdf(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    make_passport(client, ctx.siti_id)

    resp = client.get(f"/passports/{ctx.siti_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


@needs_weasyprint
def test_shared_pdf_without_login(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    make_passport(client, ctx.siti_id)
    link = client.post(f"/passports/{ctx.siti_id}/share-links").json()
    client.post("/auth/logout")

    resp = client.get(f"/share/{link['token']}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


# ------------------------------------------------------------------ エンドポイント認可

def test_pdf_requires_auth(client: TestClient, ctx) -> None:
    assert client.get(f"/passports/{ctx.siti_id}/pdf").status_code == 401


def test_pdf_404_without_passport(client: TestClient, ctx) -> None:
    login(client, "teacher@example.com")
    assert client.get(f"/passports/{ctx.siti_id}/pdf").status_code == 404


def test_pdf_503_when_renderer_unavailable(client: TestClient, ctx, monkeypatch) -> None:
    """WeasyPrint が無い環境では 500 ではなく 503 を返す。"""
    login(client, "teacher@example.com")
    make_passport(client, ctx.siti_id)
    monkeypatch.setattr(pdf_service, "is_available", lambda: False)
    assert client.get(f"/passports/{ctx.siti_id}/pdf").status_code == 503
