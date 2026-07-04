from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAtMixin, PortableJSON, str_enum
from app.models.enums import ConversationRole, Sector, SessionMode, SessionStatus, TurnRole


class PronunciationAttempt(CreatedAtMixin, Base):
    __tablename__ = "pronunciation_attempts"
    __table_args__ = (Index("ix_pronunciation_attempts_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"), index=True)
    # accuracy / fluency / completeness + 単語・音素スコア。prosody は ja-JP 非対応のため含めない。
    scores: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    weak_words: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)


class ConversationSession(CreatedAtMixin, Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(64))
    sector: Mapped[Sector] = mapped_column(str_enum(Sector, "sector"))
    mode: Mapped[SessionMode] = mapped_column(str_enum(SessionMode, "session_mode"))
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "session_status"), default=SessionStatus.IN_PROGRESS
    )

    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="session", order_by="ConversationTurn.seq"
    )


class ConversationTurn(CreatedAtMixin, Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[ConversationRole] = mapped_column(str_enum(ConversationRole, "conversation_role"))
    text_ja: Mapped[str] = mapped_column(Text)
    # partner ターンの furigana / hint_id など表示用の付随情報。
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)

    session: Mapped[ConversationSession] = relationship(back_populates="turns")


class InterviewSession(CreatedAtMixin, Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(64))
    sector: Mapped[Sector] = mapped_column(str_enum(Sector, "sector"))
    mode: Mapped[SessionMode] = mapped_column(str_enum(SessionMode, "session_mode"))
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "session_status"), default=SessionStatus.IN_PROGRESS
    )

    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session", order_by="InterviewTurn.seq"
    )
    evaluation: Mapped["InterviewEvaluation | None"] = relationship(back_populates="session")


class InterviewTurn(CreatedAtMixin, Base):
    __tablename__ = "interview_turns"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[TurnRole] = mapped_column(str_enum(TurnRole, "turn_role"))
    text_ja: Mapped[str] = mapped_column(Text)
    stt: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON)
    # interviewer ターンの furigana / hint_id / prompt_version など表示用の付随情報。
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)

    session: Mapped[InterviewSession] = relationship(back_populates="turns")


class InterviewEvaluation(CreatedAtMixin, Base):
    __tablename__ = "interview_evaluations"
    __table_args__ = (CheckConstraint("total >= 0 AND total <= 100", name="total_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), unique=True)
    rubric_version: Mapped[str] = mapped_column(String(32))
    scores: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    feedback: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    total: Mapped[int] = mapped_column(Integer)
    # 添削キュー用。NULL = 教師未確認。確認した教師と日時を記録する。
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    session: Mapped[InterviewSession] = relationship(back_populates="evaluation")


class MockSession(CreatedAtMixin, Base):
    __tablename__ = "mock_sessions"
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100", name="score_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    num_questions: Mapped[int] = mapped_column(Integer)
    num_correct: Mapped[int] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)


class QuizAttempt(CreatedAtMixin, Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("quiz_items.id"), index=True)
    mock_session_id: Mapped[int | None] = mapped_column(ForeignKey("mock_sessions.id"))
    selected_index: Mapped[int] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean)
