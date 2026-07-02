from pydantic import BaseModel, Field

from app.models.enums import ConversationRole, SessionStatus


class ScenarioOut(BaseModel):
    key: str
    title_ja: str
    title_id: str
    description_id: str
    level: str
    max_student_turns: int


class TurnOut(BaseModel):
    seq: int
    role: ConversationRole
    text_ja: str
    furigana: str | None = None
    hint_id: str | None = None


class SessionCreateIn(BaseModel):
    scenario: str


class SessionOut(BaseModel):
    session_id: int
    scenario: str
    status: SessionStatus
    max_student_turns: int
    turns: list[TurnOut]
    done: bool


class ReplyIn(BaseModel):
    text_ja: str = Field(min_length=1, max_length=500)


class ReplyOut(BaseModel):
    student_turn: TurnOut
    partner_turn: TurnOut
    done: bool
