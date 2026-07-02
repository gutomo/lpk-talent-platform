from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app import models  # noqa: F401
from app.db import Base

EXPECTED_TABLES = {
    "auth_sessions",
    "organizations",
    "users",
    "cohorts",
    "enrollments",
    "content_items",
    "pronunciation_attempts",
    "conversation_sessions",
    "interview_sessions",
    "interview_turns",
    "interview_evaluations",
    "quiz_items",
    "quiz_attempts",
    "mock_sessions",
    "attendance_records",
    "attitude_reviews",
    "passports",
    "share_links",
    "events",
}


def test_all_expected_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_tables_compile_on_postgres_dialect():
    for table in Base.metadata.tables.values():
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert table.name in ddl


def test_score_range_constraints_present():
    eval_checks = {c.name for c in models.InterviewEvaluation.__table__.constraints}
    assert "ck_interview_evaluations_total_range" in eval_checks
    mock_checks = {c.name for c in models.MockSession.__table__.constraints}
    assert "ck_mock_sessions_score_range" in mock_checks


def test_share_link_token_is_unique():
    token_col = models.ShareLink.__table__.c.token
    assert token_col.unique


def test_interview_evaluation_requires_rubric_version():
    col = models.InterviewEvaluation.__table__.c.rubric_version
    assert not col.nullable
