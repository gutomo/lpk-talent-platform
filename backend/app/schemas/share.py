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


class CompanyShareLinkOut(BaseModel):
    """組織単位の企業向け共有リンク（admin の発行・失効UI用）。"""

    id: int
    token: str
    created_at: datetime
    expires_at: datetime
    revoked: bool
    active: bool
    views: int
    last_viewed_at: datetime | None


class CandidateRow(BaseModel):
    """候補者比較テーブルの1行。最新版 Passport snapshot の要約。リスクフラグは含めない。"""

    student_id: int
    name: str
    cohort: str | None
    sector: str | None
    passport_version: int
    generated_at: datetime
    level_current: str | None
    pron_avg_accuracy: int | None
    interview_sessions: int
    interview_latest_total: int | None
    attendance_rate: int | None
    checklist_done: int
    checklist_total: int


class SharedCandidatesOut(BaseModel):
    """企業リンクの比較テーブルビュー全体。"""

    lpk_name: str
    expires_at: datetime
    candidates: list[CandidateRow]
