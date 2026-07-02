from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.models import Cohort, ConversationSession, ConversationTurn, Enrollment, User
from app.models.enums import (
    ConversationRole,
    Sector,
    SessionMode,
    SessionStatus,
    UserRole,
)
from app.routers.deps import DbSession, require_role
from app.schemas.conversation import (
    ReplyIn,
    ReplyOut,
    ScenarioOut,
    SessionCreateIn,
    SessionOut,
    TurnOut,
)
from app.services.conversation import (
    PROMPT_VERSION,
    SCENARIOS,
    LlmProviderError,
    generate_reply,
)
from app.services.events import log_event

router = APIRouter(prefix="/conversation", tags=["conversation"])

Student = Annotated[User, Depends(require_role(UserRole.STUDENT))]


def _turn_out(turn: ConversationTurn) -> TurnOut:
    return TurnOut(
        seq=turn.seq,
        role=turn.role,
        text_ja=turn.text_ja,
        furigana=turn.meta.get("furigana"),
        hint_id=turn.meta.get("hint_id"),
    )


def _session_out(session: ConversationSession, turns: list[ConversationTurn]) -> SessionOut:
    return SessionOut(
        session_id=session.id,
        scenario=session.scenario,
        status=session.status,
        max_student_turns=SCENARIOS[session.scenario]["max_student_turns"],
        turns=[_turn_out(t) for t in turns],
        done=session.status == SessionStatus.COMPLETED,
    )


@router.get("/scenarios")
def list_scenarios(student: Student) -> list[ScenarioOut]:
    """会話練習シナリオの一覧（自己紹介 / 職場会話 / 報連相）。"""
    return [
        ScenarioOut(
            key=key,
            title_ja=s["title_ja"],
            title_id=s["title_id"],
            description_id=s["description_id"],
            level=s["level"],
            max_student_turns=s["max_student_turns"],
        )
        for key, s in SCENARIOS.items()
    ]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(student: Student, db: DbSession, body: SessionCreateIn) -> SessionOut:
    """会話セッションを開始し、AIの開幕ターンを返す。"""
    scenario = SCENARIOS.get(body.scenario)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")

    sector = db.execute(
        select(Cohort.sector)
        .join(Enrollment, Enrollment.cohort_id == Cohort.id)
        .where(Enrollment.user_id == student.id)
        .limit(1)
    ).scalar_one_or_none()
    session = ConversationSession(
        user_id=student.id,
        scenario=body.scenario,
        sector=sector or Sector.GENERAL,
        mode=SessionMode.TEXT,
    )
    db.add(session)
    db.flush()
    opening = scenario["opening"]
    turn = ConversationTurn(
        session_id=session.id,
        seq=1,
        role=ConversationRole.PARTNER,
        text_ja=opening["text_ja"],
        meta={
            "furigana": opening["furigana"],
            "hint_id": opening["hint_id"],
            "prompt_version": PROMPT_VERSION,
        },
    )
    db.add(turn)
    log_event(
        db,
        student.id,
        "conversation_started",
        {"session_id": session.id, "scenario": body.scenario},
    )
    db.commit()
    return _session_out(session, [turn])


@router.post("/sessions/{session_id}/reply")
def reply(student: Student, db: DbSession, session_id: int, body: ReplyIn) -> ReplyOut:
    """学生の発話を記録し、AIの返答を生成して返す。上限到達で会話を完了にする。"""
    session = db.get(ConversationSession, session_id)
    if session is None or session.user_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.status != SessionStatus.IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session already finished")

    turns = list(
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.session_id == session.id)
            .order_by(ConversationTurn.seq)
        ).scalars()
    )
    student_turns = sum(1 for t in turns if t.role == ConversationRole.STUDENT) + 1
    history = [(t.role, t.text_ja) for t in turns] + [
        (ConversationRole.STUDENT, body.text_ja)
    ]
    try:
        result = generate_reply(session.scenario, history, student_turns)
    except LlmProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"llm_provider: {exc}") from exc

    student_turn = ConversationTurn(
        session_id=session.id,
        seq=turns[-1].seq + 1,
        role=ConversationRole.STUDENT,
        text_ja=body.text_ja,
    )
    partner_turn = ConversationTurn(
        session_id=session.id,
        seq=turns[-1].seq + 2,
        role=ConversationRole.PARTNER,
        text_ja=result["reply_ja"],
        meta={
            "furigana": result["reply_furigana"],
            "hint_id": result["hint_id"],
            "prompt_version": PROMPT_VERSION,
        },
    )
    db.add_all([student_turn, partner_turn])
    if result["done"]:
        session.status = SessionStatus.COMPLETED
        log_event(
            db,
            student.id,
            "conversation_completed",
            {
                "session_id": session.id,
                "scenario": session.scenario,
                "student_turns": student_turns,
            },
        )
    db.commit()
    return ReplyOut(
        student_turn=_turn_out(student_turn),
        partner_turn=_turn_out(partner_turn),
        done=result["done"],
    )
