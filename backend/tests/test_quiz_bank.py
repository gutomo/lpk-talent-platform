from collections import Counter

from app.content import load_quiz_bank
from app.models.enums import QuizSection

# BUILD_PLAN Phase 3: 文法40 / 語彙40 / 読解20 の100問 + 模試listening用12問
EXPECTED_COUNTS = {
    "grammar": 40,
    "vocabulary": 40,
    "reading": 20,
    "listening": 12,
}

VALID_LEVELS = ("N4", "JFT-Basic")


def test_bank_has_version_and_expected_counts() -> None:
    bank = load_quiz_bank()
    assert bank["version"]
    assert "オリジナル" in bank["license_note"], "完全オリジナル方針の明記が必要"
    counts = Counter(q["section"] for q in bank["items"])
    assert dict(counts) == EXPECTED_COUNTS
    assert len(bank["items"]) == 112


def test_sections_and_levels_are_valid() -> None:
    for q in load_quiz_bank()["items"]:
        assert QuizSection(q["section"])
        assert q["level"] in VALID_LEVELS, f"levelタグが不正: {q['question']}"


def test_choices_and_answer_index_are_consistent() -> None:
    for q in load_quiz_bank()["items"]:
        choices = q["choices"]
        assert len(choices) == 4, f"選択肢は4つ: {q['question']}"
        assert len(set(choices)) == 4, f"選択肢が重複: {q['question']}"
        assert 0 <= q["answer_index"] < 4, f"answer_index が範囲外: {q['question']}"
        assert q["question"].strip()
        assert q["explanation_id"].strip(), f"解説（id）が空: {q['question']}"


def test_questions_are_unique() -> None:
    items = load_quiz_bank()["items"]
    # 読解・聴解は同型の設問文（内容と合っているものは〜等）を許すので、本文とペアで一意性を見る。
    keys = [
        (
            q["question"],
            q.get("meta", {}).get("passage_ja", ""),
            q.get("meta", {}).get("script_ja", ""),
        )
        for q in items
    ]
    assert len(keys) == len(set(keys)), "設問が重複している"


def test_answer_positions_are_spread() -> None:
    """正解の位置が偏ると勘で解けてしまうため、どの位置も4割未満に抑える。"""
    items = load_quiz_bank()["items"]
    counts = Counter(q["answer_index"] for q in items)
    for index, count in counts.items():
        assert count < len(items) * 0.4, f"正解位置 {index} に偏りすぎ（{count}問）"


def test_reading_has_passage_and_listening_has_script() -> None:
    for q in load_quiz_bank()["items"]:
        meta = q.get("meta", {})
        if q["section"] == "reading":
            assert meta.get("passage_ja", "").strip(), f"読解に本文が無い: {q['question']}"
        elif q["section"] == "listening":
            assert meta.get("script_ja", "").strip(), f"聴解にスクリプトが無い: {q['question']}"
        else:
            assert "passage_ja" not in meta and "script_ja" not in meta
