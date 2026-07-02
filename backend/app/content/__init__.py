"""コンテンツバンク。

発音練習フレーズは完全オリジナル（JLPT / JFT の過去問・公式問題は複製しない）。
バンクはバージョン付き JSON で管理し、seed 時に content_items へ投入する。
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONTENT_DIR = Path(__file__).resolve().parent

PHRASE_BANK_FILE = "pronunciation_phrases_v1.json"


@lru_cache
def load_phrase_bank() -> dict[str, Any]:
    """発音フレーズバンク（version, phrases[{sector, text_ja, furigana, gloss_id, level}]）。"""
    with open(_CONTENT_DIR / PHRASE_BANK_FILE, encoding="utf-8") as f:
        return json.load(f)
