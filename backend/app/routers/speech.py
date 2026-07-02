from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.models import Cohort, ContentItem, Enrollment, PronunciationAttempt, User
from app.models.enums import ContentModule, Sector, UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.speech import AssessmentOut, PronunciationItemOut, WeakWordAgg
from app.services.audio import AudioConversionError
from app.services.events import log_event
from app.services.speech import (
    NoSpeechRecognizedError,
    SpeechProviderError,
    assess_pronunciation,
    extract_weak_words,
)

router = APIRouter(prefix="/speech", tags=["speech"])

Student = Annotated[User, Depends(require_role(UserRole.STUDENT))]

# 発音評価は30秒以内の想定（Azure REST の上限）。WebM/Opus 30秒は百数十KB程度なので余裕を持たせる。
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# 弱点語集計は直近の試行に限定し、古い履歴が居座らないようにする。
WEAK_WORDS_RECENT_ATTEMPTS = 50
WEAK_WORDS_LIMIT = 10


@router.get("/items")
def list_items(student: Student, db: DbSession) -> list[PronunciationItemOut]:
    """発音課題文の一覧。所属コースの職種 + 汎用のみ返す（未所属なら全件）。"""
    sector = db.execute(
        select(Cohort.sector)
        .join(Enrollment, Enrollment.cohort_id == Cohort.id)
        .where(Enrollment.user_id == student.id)
        .limit(1)
    ).scalar_one_or_none()
    stmt = select(ContentItem).where(ContentItem.module == ContentModule.PRONUNCIATION)
    if sector is not None and sector != Sector.GENERAL:
        stmt = stmt.where(ContentItem.sector.in_([sector, Sector.GENERAL]))
    items = db.execute(stmt.order_by(ContentItem.id)).scalars().all()
    return [
        PronunciationItemOut(
            id=i.id, sector=i.sector, text_ja=i.text_ja,
            furigana=i.furigana, gloss_id=i.gloss_id, level=i.level,
        )
        for i in items
    ]


@router.get("/weak-words")
def list_weak_words(student: Student, db: DbSession) -> list[WeakWordAgg]:
    """直近の試行から弱点語を集計する。語ごとに最低 accuracy と出現回数、低い順。"""
    recent = db.execute(
        select(PronunciationAttempt.weak_words)
        .where(PronunciationAttempt.user_id == student.id)
        .order_by(PronunciationAttempt.created_at.desc(), PronunciationAttempt.id.desc())
        .limit(WEAK_WORDS_RECENT_ATTEMPTS)
    ).scalars().all()
    agg: dict[str, WeakWordAgg] = {}
    for weak_list in recent:
        for w in weak_list or []:
            entry = agg.get(w["word"])
            if entry is None:
                agg[w["word"]] = WeakWordAgg(word=w["word"], accuracy=w["accuracy"], count=1)
            else:
                entry.count += 1
                entry.accuracy = min(entry.accuracy, w["accuracy"])
    return sorted(agg.values(), key=lambda e: e.accuracy)[:WEAK_WORDS_LIMIT]


@router.post("/assess")
def assess(
    student: Student,
    db: DbSession,
    item_id: Annotated[int, Form()],
    audio: Annotated[UploadFile, File()],
) -> AssessmentOut:
    """課題文の読み上げ音声を評価し、pronunciation_attempts に保存して結果を返す。"""
    item = db.get(ContentItem, item_id)
    if item is None or item.module != ContentModule.PRONUNCIATION:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content item not found")

    data = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio file too large")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty audio upload")

    try:
        result = assess_pronunciation(data, item.text_ja)
    except AudioConversionError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"audio_invalid: {exc}"
        ) from exc
    except NoSpeechRecognizedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"no_speech: {exc}") from exc
    except SpeechProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"speech_provider: {exc}") from exc

    weak_words = extract_weak_words(result)
    attempt = PronunciationAttempt(
        user_id=student.id, item_id=item.id, scores=result, weak_words=weak_words
    )
    db.add(attempt)
    db.flush()
    log_event(
        db,
        student.id,
        "pronunciation_attempt",
        {"attempt_id": attempt.id, "item_id": item.id, "accuracy": result["accuracy"]},
    )
    db.commit()

    return AssessmentOut(
        attempt_id=attempt.id,
        item_id=item.id,
        provider=result["provider"],
        accuracy=result["accuracy"],
        fluency=result["fluency"],
        completeness=result["completeness"],
        pron=result["pron"],
        recognized_text=result["recognized_text"],
        words=result["words"],
        weak_words=weak_words,
    )
