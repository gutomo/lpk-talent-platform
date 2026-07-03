"""問題生成スクリプト（Phase 3）のテスト。

要点：生成→保存は必ず review_flag=True（レビュー待ち）になり、承認するまで
デイリークイズ・模試のどちらにも出題されないこと。
"""

import random

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.models.enums import QuizSection
from app.services.drill import build_daily_quiz, build_mock_exam
from app.services.quiz_gen import (
    PROMPT_VERSION,
    LlmProviderError,
    approve_items,
    generate_drafts,
    list_pending,
    parse_drafts_response,
    save_drafts,
    validate_draft,
)

GOOD_DRAFT = {
    "question": "しごとの まえに てを（　）ます。",
    "choices": ["あらい", "たべ", "ねむり", "はしり"],
    "answer_index": 0,
    "explanation_id": "Sebelum bekerja kita mencuci (araimasu) tangan.",
}


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            models.QuizItem.__table__,
            models.QuizAttempt.__table__,
            models.MockSession.__table__,
            models.User.__table__,
            models.Organization.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# ------------------------------------------------------------------ generate


def test_stub_generates_valid_drafts_for_all_sections() -> None:
    for section in QuizSection:
        drafts = generate_drafts(section, 3)
        assert len(drafts) == 3
        for draft in drafts:
            assert validate_draft(section, draft) == []
        # 連番付与で設問が一意になる（同一バッチ内の重複防止）
        assert len({d["question"] for d in drafts}) == 3


def test_generate_rejects_unknown_level() -> None:
    with pytest.raises(ValueError):
        generate_drafts(QuizSection.GRAMMAR, 1, level="N1")


def test_validate_draft_catches_bad_shapes() -> None:
    assert validate_draft(QuizSection.GRAMMAR, {**GOOD_DRAFT, "question": " "}) != []
    assert validate_draft(QuizSection.GRAMMAR, {**GOOD_DRAFT, "choices": ["あ"] * 4}) != []
    assert validate_draft(QuizSection.GRAMMAR, {**GOOD_DRAFT, "choices": ["あ", "い", "う"]}) != []
    assert validate_draft(QuizSection.GRAMMAR, {**GOOD_DRAFT, "answer_index": 4}) != []
    assert validate_draft(QuizSection.GRAMMAR, {**GOOD_DRAFT, "explanation_id": ""}) != []
    assert validate_draft(QuizSection.READING, GOOD_DRAFT) != [], "読解は passage_ja 必須"
    assert validate_draft(QuizSection.LISTENING, GOOD_DRAFT) != [], "聴解は script_ja 必須"
    assert validate_draft(QuizSection.GRAMMAR, GOOD_DRAFT) == []


def test_parse_drafts_response_requires_tool_and_items() -> None:
    ok = {
        "output": {
            "message": {
                "content": [{"toolUse": {"name": "draft_items", "input": {"items": [GOOD_DRAFT]}}}]
            }
        }
    }
    assert parse_drafts_response(ok) == [GOOD_DRAFT]
    with pytest.raises(LlmProviderError):
        parse_drafts_response({"output": {"message": {"content": [{"text": "こんにちは"}]}}})
    with pytest.raises(LlmProviderError):
        parse_drafts_response(
            {
                "output": {
                    "message": {
                        "content": [{"toolUse": {"name": "draft_items", "input": {"items": []}}}]
                    }
                }
            }
        )


# -------------------------------------------------------------- save / review


def test_save_drafts_marks_review_flag_and_meta(session_factory) -> None:
    with session_factory() as db:
        drafts = generate_drafts(QuizSection.READING, 2)
        items = save_drafts(db, QuizSection.READING, "N4", drafts, topic_ja="介護のしごと")
        db.commit()

        saved = db.execute(select(models.QuizItem)).scalars().all()
        assert len(saved) == 2
        for item in saved:
            assert item.review_flag is True, "人間レビュー前は必ず出題対象外"
            assert item.meta["source"] == "llm-draft"
            assert item.meta["prompt_version"] == PROMPT_VERSION
            assert item.meta["topic_ja"] == "介護のしごと"
            assert item.meta["passage_ja"]
        assert [i.id for i in items] == [i.id for i in saved]


def test_save_drafts_rejects_invalid_draft(session_factory) -> None:
    with session_factory() as db:
        bad = {**GOOD_DRAFT, "answer_index": 9}
        with pytest.raises(ValueError):
            save_drafts(db, QuizSection.GRAMMAR, "N4", [bad])


def test_drafts_are_not_served_until_approved(session_factory) -> None:
    with session_factory() as db:
        # 承認済みの既存バンク相当（模試が組める最低限）を投入
        for section, count in (
            (QuizSection.GRAMMAR, 10),
            (QuizSection.VOCABULARY, 10),
            (QuizSection.READING, 6),
            (QuizSection.LISTENING, 5),
        ):
            for n in range(count):
                meta = {}
                if section == QuizSection.READING:
                    meta["passage_ja"] = f"本文{n}"
                if section == QuizSection.LISTENING:
                    meta["script_ja"] = f"スクリプト{n}"
                db.add(
                    models.QuizItem(
                        section=section,
                        level="N4",
                        question=f"{section.value}の問題{n}",
                        choices=["あ", "い", "う", "え"],
                        answer_index=1,
                        explanation_id=f"Penjelasan {n}",
                        review_flag=False,
                        meta=meta,
                    )
                )
        drafts = save_drafts(db, QuizSection.GRAMMAR, "N4", generate_drafts(QuizSection.GRAMMAR, 3))
        db.commit()
        draft_ids = {i.id for i in drafts}

        from datetime import date

        daily, _ = build_daily_quiz(db, user_id=1, today=date(2026, 7, 3))
        assert draft_ids.isdisjoint({i.id for i in daily}), "レビュー待ちはデイリーに出さない"
        mock = build_mock_exam(db, random.Random(0))
        assert draft_ids.isdisjoint({i.id for i in mock}), "レビュー待ちは模試に出さない"

        # 承認すると出題プールに入る
        approve_items(db, sorted(draft_ids))
        db.commit()
        assert list_pending(db) == []
        pool = {
            i.id
            for i in db.execute(
                select(models.QuizItem).where(models.QuizItem.review_flag.is_(False))
            ).scalars()
        }
        assert draft_ids <= pool


def test_approve_rejects_unknown_or_already_approved(session_factory) -> None:
    with session_factory() as db:
        items = save_drafts(db, QuizSection.GRAMMAR, "N4", generate_drafts(QuizSection.GRAMMAR, 1))
        db.commit()
        approve_items(db, [items[0].id])
        db.commit()
        with pytest.raises(ValueError):
            approve_items(db, [items[0].id])  # 既に承認済み
        with pytest.raises(ValueError):
            approve_items(db, [99999])
