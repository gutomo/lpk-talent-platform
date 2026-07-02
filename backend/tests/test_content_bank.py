import re
from collections import Counter

from app.content import load_phrase_bank
from app.models.enums import Sector

# BUILD_PLAN Phase 1: 介護40 / 食品製造20 / 外食20 / 汎用40
EXPECTED_COUNTS = {
    "kaigo": 40,
    "food_manufacturing": 20,
    "restaurant": 20,
    "general": 40,
}

KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def test_bank_has_version_and_expected_counts() -> None:
    bank = load_phrase_bank()
    assert bank["version"]
    counts = Counter(p["sector"] for p in bank["phrases"])
    assert dict(counts) == EXPECTED_COUNTS
    assert len(bank["phrases"]) == 120


def test_sectors_are_valid_enum_values() -> None:
    for phrase in load_phrase_bank()["phrases"]:
        assert Sector(phrase["sector"])


def test_text_ja_is_unique_and_reasonable_length() -> None:
    phrases = load_phrase_bank()["phrases"]
    texts = [p["text_ja"] for p in phrases]
    assert len(texts) == len(set(texts)), "text_ja が重複している"
    for text in texts:
        assert 4 <= len(text) <= 45, f"長さが不自然: {text}"


def test_furigana_contains_no_kanji() -> None:
    for phrase in load_phrase_bank()["phrases"]:
        assert phrase["furigana"], f"furigana が空: {phrase['text_ja']}"
        assert not KANJI.search(phrase["furigana"]), (
            f"furigana に漢字が残っている: {phrase['furigana']}"
        )


def test_gloss_and_level_present() -> None:
    for phrase in load_phrase_bank()["phrases"]:
        assert phrase["gloss_id"].strip(), f"gloss_id が空: {phrase['text_ja']}"
        assert phrase["level"] in ("A1", "A2")
