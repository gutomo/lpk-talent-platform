from pydantic import BaseModel, Field

from app.models.enums import Sector, SessionStatus, TurnRole


class ScenarioOut(BaseModel):
    key: str
    title_ja: str
    title_id: str
    description_id: str
    level: str
    sector: Sector
    max_candidate_turns: int


class TurnOut(BaseModel):
    seq: int
    role: TurnRole
    text_ja: str
    furigana: str | None = None
    hint_id: str | None = None


class ModelAnswerOut(BaseModel):
    question_ja: str
    answer_ja: str


class EvaluationOut(BaseModel):
    rubric_version: str
    scores: dict[str, int]
    total: int
    summary_id: str | None = None
    summary_ja: str | None = None
    advice_id: str | None = None
    model_answers: list[ModelAnswerOut] = Field(default_factory=list)


class SessionCreateIn(BaseModel):
    scenario: str


class SessionOut(BaseModel):
    session_id: int
    scenario: str
    status: SessionStatus
    max_candidate_turns: int
    turns: list[TurnOut]
    done: bool
    evaluation: EvaluationOut | None = None


class ReplyIn(BaseModel):
    text_ja: str = Field(min_length=1, max_length=500)


class ReplyOut(BaseModel):
    candidate_turn: TurnOut
    interviewer_turn: TurnOut
    done: bool
    # 面接完走時のみ入る。それ以外は null。
    evaluation: EvaluationOut | None = None
