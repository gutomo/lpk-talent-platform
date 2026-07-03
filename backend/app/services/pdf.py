"""Talent Passport の PDF 生成（WeasyPrint + 同梱 Noto Sans JP）。

WeasyPrint は Pango 等のネイティブライブラリを必要とし、Windows 開発機には
無いことがある。import は生成時まで遅延し、可用性は is_available() で判定する
（endpoint 側は 503 を返す）。コンテナ（Linux）では常に利用可能な前提。

豆腐（グリフ欠け）対策：font-family は同梱の Noto Sans JP のみを明示し、
テンプレートには JP サブセットに確実に含まれる文字（日本語・基本ラテン・○ ―）
だけを使う。チェックマーク等の記号は使わない。
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

APP_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = APP_DIR / "content" / "fonts"

SECTOR_LABELS_JA = {
    "kaigo": "介護",
    "food_manufacturing": "食品製造",
    "restaurant": "外食",
    "general": "汎用",
}

# frontend の生活態度チェックと同一キー・同一順（backend/app/services/records.py 参照）。
ATTITUDE_LABELS_JA = {
    "hourensou": "報連相",
    "punctuality": "時間厳守",
    "dormitory": "寮生活",
    "manner": "マナー",
    "teamwork": "協調性",
}

# PDF に載せる推移の点数。多すぎると表が伸びて A4 2枚を超えるため直近のみ。
TREND_POINTS = 6


def is_available() -> bool:
    """WeasyPrint がこの環境で使えるか（ネイティブライブラリ欠如は OSError になる）。"""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(APP_DIR / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _fmt_date(value: Any) -> str:
    """ISO文字列 / datetime を YYYY-MM-DD に揃える。想定外はそのまま文字列化。"""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return str(value)


def _score_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def build_context(version: int, created_at: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    """テンプレートに渡す表示用コンテキスト。判定や整形は全てここで済ませる。

    企業提出用の紹介シートなので、内部運用向けのリスクフラグは載せない。
    """
    student = snapshot.get("student") or {}
    level = snapshot.get("japanese_level") or {}
    pron = snapshot.get("pronunciation") or {}
    itv = snapshot.get("interview") or {}
    conv = snapshot.get("conversation") or {}
    attendance = snapshot.get("attendance") or {}
    attitude = snapshot.get("attitude")

    attitude_rows: list[dict[str, Any]] = []
    if attitude is not None:
        checklist = attitude.get("checklist") or {}
        for key, label in ATTITUDE_LABELS_JA.items():
            if key in checklist:
                attitude_rows.append({"label": label, "value": _score_or_none(checklist[key])})

    return {
        "student_name": student.get("name") or "",
        "cohort": student.get("cohort"),
        "sector_ja": SECTOR_LABELS_JA.get(student.get("sector") or "", None),
        "version": version,
        "generated_at": _fmt_date(created_at),
        "level_current": level.get("current"),
        "mock_trend": [
            {"date": _fmt_date(p.get("date")), "score": _score_or_none(p.get("score"))}
            for p in (level.get("trend") or [])[-TREND_POINTS:]
        ],
        "pron_avg": _score_or_none(pron.get("avg_accuracy")),
        "pron_attempts": pron.get("attempts") or 0,
        "weak_words": pron.get("weak_words") or [],
        "itv_latest": _score_or_none(itv.get("latest_total")),
        "itv_avg": _score_or_none(itv.get("avg_total")),
        "itv_sessions": itv.get("sessions") or 0,
        "itv_trend": [
            {"date": _fmt_date(p.get("date")), "total": _score_or_none(p.get("total"))}
            for p in (itv.get("trend") or [])[-TREND_POINTS:]
        ],
        "transcript_excerpt": itv.get("transcript_excerpt") or [],
        "conversation_completed": conv.get("completed") or 0,
        "attendance_rate": _score_or_none(attendance.get("rate")),
        "attitude_rows": attitude_rows,
        "attitude_note": (attitude or {}).get("note"),
        "attitude_reviewed_at": _fmt_date(attitude["reviewed_at"]) if attitude else None,
        "checklist": snapshot.get("checklist") or [],
    }


def render_html(version: int, created_at: Any, snapshot: dict[str, Any]) -> str:
    context = build_context(version, created_at, snapshot)
    return _env().get_template("passport_pdf.html.j2").render(**context)


def render_pdf(version: int, created_at: Any, snapshot: dict[str, Any]) -> bytes:
    """A4 の候補者紹介シート PDF を生成する。呼び出し前に is_available() を確認すること。"""
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    html = render_html(version, created_at, snapshot)
    font_config = FontConfiguration()
    # base_url を app ディレクトリにし、テンプレート内の content/fonts/... を解決させる。
    return HTML(string=html, base_url=str(APP_DIR)).write_pdf(font_config=font_config)
