from pydantic import BaseModel


class PronunciationItemOut(BaseModel):
    id: int
    sector: str
    text_ja: str
    furigana: str | None
    gloss_id: str | None
    level: str


class WeakWordAgg(BaseModel):
    """弱点語の集計行。accuracy は全試行での最低スコア。"""

    word: str
    accuracy: int
    count: int


class PhonemeScore(BaseModel):
    phoneme: str
    accuracy: int


class WordScore(BaseModel):
    word: str
    accuracy: int
    error_type: str
    phonemes: list[PhonemeScore] = []


class WeakWord(BaseModel):
    word: str
    accuracy: int


class AssessmentOut(BaseModel):
    attempt_id: int
    item_id: int
    provider: str
    accuracy: int
    fluency: int
    completeness: int
    pron: int
    recognized_text: str
    words: list[WordScore]
    weak_words: list[WeakWord]
