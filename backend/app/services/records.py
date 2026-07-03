"""教師入力（出席・生活態度）の書き込みサービス。

出席は月次%または日次（出席=100 / 欠席=0）を AttendanceRecord に記録する。
態度は5項目チェックリスト（各0〜100）を AttitudeReview に履歴として積む。
どちらも Passport 集計（app.services.passport）が読む側のデータになる。
"""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, AttitudeReview
from app.models.enums import AttendanceKind

# 態度チェックリストの5項目（key と日本語ラベル）。ラベル表示はフロントの i18n が持つが、
# キーの正がここ。報連相のみ Passport のチェックリスト判定に使われる（hourensou メトリクス）。
ATTITUDE_ITEMS: list[tuple[str, str]] = [
    ("hourensou", "報連相"),
    ("punctuality", "時間厳守"),
    ("dormitory", "寮生活"),
    ("manner", "マナー"),
    ("teamwork", "協調性"),
]
ATTITUDE_KEYS: list[str] = [key for key, _ in ATTITUDE_ITEMS]


def upsert_attendance(
    db: Session,
    *,
    user_id: int,
    kind: AttendanceKind,
    record_date: date,
    value: int,
    note: str | None,
) -> AttendanceRecord:
    """出席記録を追加または更新する。

    (user_id, kind, record_date) はユニーク制約なので、同一日への再入力は上書きする
    （教師が値を訂正しやすくするため。409 では弾かない）。commit は呼び出し側。
    """
    record = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.kind == kind,
            AttendanceRecord.record_date == record_date,
        )
    ).scalar_one_or_none()
    if record is None:
        record = AttendanceRecord(
            user_id=user_id, kind=kind, record_date=record_date, value=value, note=note
        )
        db.add(record)
    else:
        record.value = value
        record.note = note
    return record


def add_attitude_review(
    db: Session,
    *,
    user_id: int,
    reviewer_id: int,
    checklist: dict[str, int],
    note: str | None,
) -> AttitudeReview:
    """態度レビューを新規行として追加する（履歴を残す。集計は最新1件を参照）。

    checklist のキー検証はルータのスキーマ（AttitudeChecklistIn）で担保する。commit は呼び出し側。
    """
    review = AttitudeReview(
        user_id=user_id,
        reviewer_id=reviewer_id,
        checklist=checklist,
        note=note,
    )
    db.add(review)
    return review


def list_attendance(db: Session, user_id: int) -> list[AttendanceRecord]:
    """学生の出席記録を新しい日付順で返す（詳細ページの一覧・訂正用）。"""
    return list(
        db.execute(
            select(AttendanceRecord)
            .where(AttendanceRecord.user_id == user_id)
            .order_by(AttendanceRecord.record_date.desc(), AttendanceRecord.id.desc())
        ).scalars()
    )


def latest_attitude_checklist(review: AttitudeReview | None) -> dict[str, Any]:
    """フォーム prefill 用に、最新レビューの checklist を5キーで埋めて返す（欠損は0）。"""
    source = review.checklist if review is not None else {}
    return {key: int(source.get(key, 0)) for key in ATTITUDE_KEYS}
