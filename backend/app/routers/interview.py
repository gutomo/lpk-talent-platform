from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.models import InterviewEvaluation, InterviewSession, InterviewTurn, User
from app.models.enums import Sector, SessionMode, SessionStatus, TurnRole, UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.interview import (
    EvaluationOut,
    ReplyIn,
    ReplyOut,
    ScenarioOut,
    SessionCreateIn,
    SessionOut,
    TurnOut,
)
from app.services.events import log_event
from app.services.interview import (
    PROMPT_VERSION,
    RUBRIC_VERSION,
    SCENARIOS,
    LlmProviderError,
    evaluate_interview,
    generate_question,
)

router = APIRouter(prefix="/interview", tags=["interview"])

Student = Annotated[User, Depends(require_role(UserRole.STUDENT))]


def _turn_out(turn: InterviewTurn) -> TurnOut:
    return TurnOut(
        seq=turn.seq,
        role=turn.role,
        text_ja=turn.text_ja,
        furigana=turn.meta.get("furigana"),
        hint_id=turn.meta.get("hint_id"),
    )


def _evaluation_out(ev: InterviewEvaluation) -> EvaluationOut:
    return EvaluationOut(
        rubric_version=ev.rubric_version,
        scores=ev.scores,
        total=ev.total,
        summary_id=ev.feedback.get("id"),
        summary_ja=ev.feedback.get("ja"),
        advice_id=ev.feedback.get("advice_id"),
        model_answers=ev.feedback.get("model_answers", []),
    )


def _session_out(
    session: InterviewSession,
    turns: list[InterviewTurn],
    evaluation: InterviewEvaluation | None,
) -> SessionOut:
    scenario = SCENARIOS.get(session.scenario)
    # seed の旧シナリオキーは定義に無いので、実ターン数でフォールバックする。
    max_candidate_turns = (
        scenario["max_candidate_turns"]
        if scenario is not None
        else sum(1 for t in turns if t.role == TurnRole.CANDIDATE)
    )
    return SessionOut(
        session_id=session.id,
        scenario=session.scenario,
        status=session.status,
        max_candidate_turns=max_candidate_turns,
        turns=[_turn_out(t) for t in turns],
        done=session.status == SessionStatus.COMPLETED,
        evaluation=_evaluation_out(evaluation) if evaluation is not None else None,
    )


@router.get("/scenarios")
def list_scenarios(student: Student) -> list[ScenarioOut]:
    """面接シナリオの一覧（介護 / 食品製造 / 外食の優先順）。"""
    return [
        ScenarioOut(
            key=key,
            title_ja=s["title_ja"],
            title_id=s["title_id"],
            description_id=s["description_id"],
            level=s["level"],
            sector=Sector(s["sector"]),
            max_candidate_turns=s["max_candidate_turns"],
        )
        for key, s in SCENARIOS.items()
    ]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(student: Student, db: DbSession, body: SessionCreateIn) -> SessionOut:
    """面接セッションを開始し、面接官の開幕質問（自己紹介）を返す。"""
    scenario = SCENARIOS.get(body.scenario)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")

    session = InterviewSession(
        user_id=student.id,
        scenario=body.scenario,
        sector=Sector(scenario["sector"]),
        mode=SessionMode.TEXT,
    )
    db.add(session)
    db.flush()
    opening = scenario["opening"]
    turn = InterviewTurn(
        session_id=session.id,
        seq=1,
        role=TurnRole.INTERVIEWER,
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
        "interview_started",
        {"session_id": session.id, "scenario": body.scenario},
    )
    db.commit()
    return _session_out(session, [turn], None)


@router.post("/sessions/{session_id}/reply")
def reply(student: Student, db: DbSession, session_id: int, body: ReplyIn) -> ReplyOut:
    """学生の回答を記録し、面接官の次の発話を返す。完走時はルーブリック評価も保存して返す。"""
    session = db.get(InterviewSession, session_id)
    if session is None or session.user_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.status != SessionStatus.IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session already finished")

    turns = list(
        db.execute(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session.id)
            .order_by(InterviewTurn.seq)
        ).scalars()
    )
    candidate_turns = sum(1 for t in turns if t.role == TurnRole.CANDIDATE) + 1
    history = [(t.role, t.text_ja) for t in turns] + [(TurnRole.CANDIDATE, body.text_ja)]
    # 失敗時は全てロールバックされるので、最終ターンの再送でやり直せる。
    try:
        result = generate_question(session.scenario, history, candidate_turns)
        evaluation_result = (
            evaluate_interview(
                session.scenario, history + [(TurnRole.INTERVIEWER, result["question_ja"])]
            )
            if result["done"]
            else None
        )
    except LlmProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"llm_provider: {exc}") from exc

    candidate_turn = InterviewTurn(
        session_id=session.id,
        seq=turns[-1].seq + 1,
        role=TurnRole.CANDIDATE,
        text_ja=body.text_ja,
    )
    interviewer_turn = InterviewTurn(
        session_id=session.id,
        seq=turns[-1].seq + 2,
        role=TurnRole.INTERVIEWER,
        text_ja=result["question_ja"],
        meta={
            "furigana": result["furigana"],
            "hint_id": result["hint_id"],
            "prompt_version": PROMPT_VERSION,
        },
    )
    db.add_all([candidate_turn, interviewer_turn])

    evaluation = None
    if evaluation_result is not None:
        session.status = SessionStatus.COMPLETED
        evaluation = InterviewEvaluation(
            session_id=session.id,
            rubric_version=RUBRIC_VERSION,
            scores=evaluation_result["scores"],
            feedback=evaluation_result["feedback"],
            total=evaluation_result["total"],
        )
        db.add(evaluation)
        log_event(
            db,
            student.id,
            "interview_completed",
            {
                "session_id": session.id,
                "scenario": session.scenario,
                "total": evaluation_result["total"],
            },
        )
    db.commit()
    return ReplyOut(
        candidate_turn=_turn_out(candidate_turn),
        interviewer_turn=_turn_out(interviewer_turn),
        done=evaluation is not None,
        evaluation=_evaluation_out(evaluation) if evaluation is not None else None,
    )


@router.get("/sessions/{session_id}")
def get_session(student: Student, db: DbSession, session_id: int) -> SessionOut:
    """セッション詳細（全ターン + 評価があれば評価）。フィードバックの再表示用。"""
    session = db.get(InterviewSession, session_id)
    if session is None or session.user_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    turns = list(
        db.execute(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session.id)
            .order_by(InterviewTurn.seq)
        ).scalars()
    )
    evaluation = db.execute(
        select(InterviewEvaluation).where(InterviewEvaluation.session_id == session.id)
    ).scalar_one_or_none()
    return _session_out(session, turns, evaluation)
