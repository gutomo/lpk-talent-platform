from pydantic import BaseModel


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
