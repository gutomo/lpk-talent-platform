from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AttendanceKind, Sector, SessionMode, TurnRole


class StudentListItem(BaseModel):
    id: int
    name: str
    email: str
    cohort_name: str | None
    last_active_at: datetime | None
    # クラス一覧の進捗・アラート列（dashboard.class_overview のライブ集計）。
    attendance_rate: int | None
    interview_sessions: int
    interview_latest_total: int | None
    pron_avg_accuracy: int | None
    risk_level: str
    risk_flags: list[str]


class AttendanceRecordOut(BaseModel):
    id: int
    kind: AttendanceKind
    record_date: date
    value: int
    note: str | None


class PassportBrief(BaseModel):
    version: int
    created_at: datetime


class StudentDetail(BaseModel):
    id: int
    name: str
    email: str
    cohort_name: str | None
    sector: Sector | None
    # build_snapshot のライブ集計（Passport 未生成でも見える）。PDF・共有ビューと同じ形。
    summary: dict[str, Any]
    attendance_records: list[AttendanceRecordOut]
    latest_passport: PassportBrief | None


class AttendanceIn(BaseModel):
    kind: AttendanceKind = AttendanceKind.MONTHLY
    record_date: date
    value: int = Field(ge=0, le=100)
    note: str | None = Field(default=None, max_length=255)


class AttitudeChecklistIn(BaseModel):
    """態度チェックリスト5項目（各0〜100）。キー・範囲はここで厳格に検証する。"""

    hourensou: int = Field(ge=0, le=100)
    punctuality: int = Field(ge=0, le=100)
    dormitory: int = Field(ge=0, le=100)
    manner: int = Field(ge=0, le=100)
    teamwork: int = Field(ge=0, le=100)


class AttitudeIn(BaseModel):
    checklist: AttitudeChecklistIn
    note: str | None = Field(default=None, max_length=1000)


class StudentInterviewItem(BaseModel):
    """教師向けの面接履歴1行。title_ja はシナリオ定義が無い旧キーでは None。"""

    session_id: int
    scenario: str
    title_ja: str | None
    mode: SessionMode
    total: int
    created_at: datetime
    reviewed_at: datetime | None


class TranscriptTurnOut(BaseModel):
    seq: int
    role: TurnRole
    text_ja: str


class TranscriptEvaluationOut(BaseModel):
    # evaluation_id は添削キューの確認操作（/review/evaluations/{id}/complete）に使う。
    evaluation_id: int
    rubric_version: str
    scores: dict[str, Any]
    summary_ja: str | None
    summary_id: str | None
    total: int
    reviewed_at: datetime | None
    reviewer_name: str | None


class InterviewTranscriptOut(BaseModel):
    """教師向けの面接文字起こし（全ターン + 評価）。添削キューと学生詳細が共用する。"""

    session_id: int
    # 添削キューから直接開いたときに学生名を再取得せず表示するため持たせる。
    student_id: int
    student_name: str
    scenario: str
    title_ja: str | None
    mode: SessionMode
    created_at: datetime
    turns: list[TranscriptTurnOut]
    evaluation: TranscriptEvaluationOut | None
