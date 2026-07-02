from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.models import ContentItem, PronunciationAttempt, User
from app.models.enums import ContentModule, UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.speech import AssessmentOut
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
