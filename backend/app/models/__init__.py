# すべてのモデルをここで import し、Base.metadata への登録と Alembic autogenerate を保証する。
from app.models.auth import AuthSession
from app.models.content import ContentItem, QuizItem
from app.models.event import Event
from app.models.org import Cohort, Enrollment, Organization, User
from app.models.passport import CompanyShareLink, Passport, ShareLink
from app.models.practice import (
    ConversationSession,
    ConversationTurn,
    InterviewEvaluation,
    InterviewSession,
    InterviewTurn,
    MockSession,
    PronunciationAttempt,
    QuizAttempt,
)
from app.models.records import AttendanceRecord, AttitudeReview

__all__ = [
    "AttendanceRecord",
    "AttitudeReview",
    "AuthSession",
    "Cohort",
    "CompanyShareLink",
    "ContentItem",
    "ConversationSession",
    "ConversationTurn",
    "Enrollment",
    "Event",
    "InterviewEvaluation",
    "InterviewSession",
    "InterviewTurn",
    "MockSession",
    "Organization",
    "Passport",
    "PronunciationAttempt",
    "QuizAttempt",
    "QuizItem",
    "ShareLink",
    "User",
]
