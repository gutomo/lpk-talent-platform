from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AttendanceKind, Sector


class StudentListItem(BaseModel):
    id: int
    name: str
    email: str
    cohort_name: str | None
    last_active_at: datetime | None


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
