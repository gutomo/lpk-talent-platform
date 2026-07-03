from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import QuizSection


class QuizItemOut(BaseModel):
    """出題用の問題。answer_index / explanation_id は解答後にのみ返す（漏洩防止）。

    script_ja は聴解のみ。Azure TTS が使えない stub モードで browser TTS の読み上げに
    使うために返す（画面には表示しない前提）。
    """

    item_id: int
    section: QuizSection
    level: str
    question: str
    choices: list[str]
    passage_ja: str | None = None
    script_ja: str | None = None
    is_review: bool = False


class DailyQuizOut(BaseModel):
    items: list[QuizItemOut]
    review_count: int


class AnswerIn(BaseModel):
    item_id: int
    selected_index: int = Field(ge=0, le=3)


class AnswerOut(BaseModel):
    is_correct: bool
    correct_index: int
    explanation_id: str | None


class MockExamOut(BaseModel):
    items: list[QuizItemOut]
    num_questions: int


class MockSubmitIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1)


class MockQuestionResultOut(BaseModel):
    item_id: int
    is_correct: bool
    correct_index: int
    explanation_id: str | None


class MockResultOut(BaseModel):
    mock_id: int
    score: int
    num_questions: int
    num_correct: int
    band: str | None
    results: list[MockQuestionResultOut]


class MockHistoryItemOut(BaseModel):
    mock_id: int
    score: int
    num_questions: int
    num_correct: int
    created_at: datetime
