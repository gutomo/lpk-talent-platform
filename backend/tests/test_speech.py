import base64
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.config import Settings
from app.db import Base, get_db
from app.main import app
from app.models.enums import ContentModule, Locale, OrgType, Sector, UserRole
from app.services import speech
from app.services.auth import hash_password

TABLES = [
    models.Organization.__table__,
    models.User.__table__,
    models.AuthSession.__table__,
    models.Event.__table__,
    models.ContentItem.__table__,
    models.PronunciationAttempt.__table__,
]

PASSWORD = "rahasia123"
FAKE_AUDIO = b"\x1aE\xdf\xa3 fake webm bytes for stub provider"


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        lpk = models.Organization(name="LPK Test", type=OrgType.LPK)
        db.add(lpk)
        db.flush()
        pw = hash_password(PASSWORD)
        db.add_all([
            models.User(org_id=lpk.id, role=UserRole.STUDENT, locale=Locale.ID,
                        name="Siti Rahma", email="siti@example.com", password_hash=pw),
            models.User(org_id=lpk.id, role=UserRole.TEACHER, locale=Locale.JA,
                        name="田中 美咲", email="teacher@example.com", password_hash=pw),
        ])
        db.add_all([
            models.ContentItem(id=1, module=ContentModule.PRONUNCIATION, sector=Sector.KAIGO,
                               text_ja="朝の検温の時間です。体温を測りますね。",
                               furigana="あさのけんおんのじかんです。たいおんをはかりますね。",
                               gloss_id="Sekarang waktunya pengukuran suhu pagi.",
                               level="A2", meta={}),
            models.ContentItem(id=2, module=ContentModule.DRILL, sector=Sector.GENERAL,
                               text_ja="ドリル用アイテム", furigana=None, gloss_id=None,
                               level="A2", meta={}),
        ])
        db.commit()
    return factory


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, email: str) -> None:
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


def post_assess(client: TestClient, item_id: int = 1, audio: bytes = FAKE_AUDIO):
    return client.post(
        "/speech/assess",
        data={"item_id": item_id},
        files={"audio": ("rec.webm", audio, "audio/webm")},
    )


# ------------------------------------------------------------------- endpoint


def test_assess_requires_auth(client: TestClient) -> None:
    assert post_assess(client).status_code == 401


def test_assess_rejects_teacher_role(client: TestClient) -> None:
    login(client, "teacher@example.com")
    assert post_assess(client).status_code == 403


def test_assess_unknown_item_returns_404(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert post_assess(client, item_id=999).status_code == 404


def test_assess_drill_item_returns_404(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert post_assess(client, item_id=2).status_code == 404


def test_assess_empty_audio_returns_422(client: TestClient) -> None:
    login(client, "siti@example.com")
    assert post_assess(client, audio=b"").status_code == 422


def test_assess_stub_happy_path_persists_attempt_and_event(
    client: TestClient, session_factory
) -> None:
    login(client, "siti@example.com")
    resp = post_assess(client)
    assert resp.status_code == 200
    body = resp.json()

    for key in ("accuracy", "fluency", "completeness", "pron"):
        assert 0 <= body[key] <= 100
    assert body["provider"] == "stub"
    assert body["item_id"] == 1
    assert body["words"], "単語別スコアが返ること"
    assert all(0 <= w["accuracy"] <= 100 for w in body["words"])
    # 弱点語は閾値未満か誤読・脱落の語のみ。
    word_scores = {w["word"]: w for w in body["words"]}
    for weak in body["weak_words"]:
        w = word_scores[weak["word"]]
        assert (
            w["accuracy"] < speech.WEAK_WORD_THRESHOLD
            or w["error_type"] in ("Mispronunciation", "Omission")
        )

    with session_factory() as db:
        attempt = db.get(models.PronunciationAttempt, body["attempt_id"])
        assert attempt is not None
        assert attempt.scores["accuracy"] == body["accuracy"]
        assert attempt.weak_words == body["weak_words"]
        event = db.execute(
            select(models.Event).where(models.Event.type == "pronunciation_attempt")
        ).scalar_one()
        assert event.user_id == attempt.user_id
        assert event.meta["attempt_id"] == attempt.id
        assert event.meta["accuracy"] == body["accuracy"]


def test_assess_is_deterministic_in_stub_mode(client: TestClient) -> None:
    login(client, "siti@example.com")
    first = post_assess(client).json()
    second = post_assess(client).json()
    assert first["accuracy"] == second["accuracy"]
    assert first["words"] == second["words"]


def test_assess_maps_no_speech_to_422(client: TestClient, monkeypatch) -> None:
    def boom(audio_bytes, reference_text):
        raise speech.NoSpeechRecognizedError("InitialSilenceTimeout")

    monkeypatch.setattr("app.routers.speech.assess_pronunciation", boom)
    login(client, "siti@example.com")
    resp = post_assess(client)
    assert resp.status_code == 422
    assert "no_speech" in resp.json()["detail"]


def test_assess_maps_provider_error_to_502(client: TestClient, monkeypatch) -> None:
    def boom(audio_bytes, reference_text):
        raise speech.SpeechProviderError("HTTP 401")

    monkeypatch.setattr("app.routers.speech.assess_pronunciation", boom)
    login(client, "siti@example.com")
    assert post_assess(client).status_code == 502


# ----------------------------------------------------------------------- stub


def test_stub_is_deterministic_and_varies_with_audio() -> None:
    text = "おはようございます。"
    a = speech.assess_stub(b"audio-1", text)
    b = speech.assess_stub(b"audio-1", text)
    c = speech.assess_stub(b"audio-2", text)
    assert a == b
    assert a != c


def test_stub_scores_within_range() -> None:
    result = speech.assess_stub(b"x", "何かあったら、すぐにナースコールを押してください。")
    for key in ("accuracy", "fluency", "completeness", "pron"):
        assert 0 <= result[key] <= 100
    assert result["words"]
    joined = "".join(w["word"] for w in result["words"])
    assert "、" not in joined and "。" not in joined


# ----------------------------------------------------------- weak word extract


def test_extract_weak_words_rules() -> None:
    result = {
        "words": [
            {"word": "検温", "accuracy": 55, "error_type": "None", "phonemes": []},
            {"word": "時間", "accuracy": 90, "error_type": "None", "phonemes": []},
            {"word": "体温", "accuracy": 85, "error_type": "Mispronunciation", "phonemes": []},
            {"word": "余分", "accuracy": 10, "error_type": "Insertion", "phonemes": []},
            {"word": "検温", "accuracy": 40, "error_type": "None", "phonemes": []},
        ]
    }
    weak = speech.extract_weak_words(result)
    assert {"word": "検温", "accuracy": 40} in weak
    assert {"word": "体温", "accuracy": 85} in weak
    assert all(w["word"] != "余分" for w in weak), "挿入語は対象外"
    assert all(w["word"] != "時間" for w in weak)
    assert len([w for w in weak if w["word"] == "検温"]) == 1, "重複語は最低スコアで1件"


# ---------------------------------------------------------------------- azure


def test_pa_header_has_no_prosody_and_correct_params() -> None:
    header = speech.build_pa_header("朝の検温の時間です。")
    params = json.loads(base64.b64decode(header))
    assert params["ReferenceText"] == "朝の検温の時間です。"
    assert params["GradingSystem"] == "HundredMark"
    assert params["Granularity"] == "Phoneme"
    assert params["Dimension"] == "Comprehensive"
    assert params["EnableMiscue"] == "True"
    # ja-JP は prosody 非対応（CLAUDE.md 地雷）。ヘッダに含めてはいけない。
    assert "EnableProsodyAssessment" not in params


def test_stt_url_region_and_custom_endpoint() -> None:
    regional = Settings(azure_speech_region="japaneast", _env_file=None)
    assert speech.stt_url(regional) == (
        "https://japaneast.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    custom = Settings(
        azure_speech_endpoint="https://myres.cognitiveservices.azure.com/", _env_file=None
    )
    assert speech.stt_url(custom) == (
        "https://myres.cognitiveservices.azure.com"
        "/stt/speech/recognition/conversation/cognitiveservices/v1"
    )


AZURE_PAYLOAD = {
    "RecognitionStatus": "Success",
    "DisplayText": "朝の検温の時間です。",
    "NBest": [
        {
            "Confidence": 0.98,
            "Lexical": "朝の検温の時間です",
            "Display": "朝の検温の時間です。",
            "AccuracyScore": 82.4,
            "FluencyScore": 91.0,
            "CompletenessScore": 100.0,
            "PronScore": 86.9,
            "Words": [
                {
                    "Word": "朝",
                    "AccuracyScore": 95.0,
                    "ErrorType": "None",
                    "Phonemes": [{"Phoneme": "a", "AccuracyScore": 96.0}],
                },
                {
                    "Word": "検温",
                    "AccuracyScore": 48.7,
                    "ErrorType": "Mispronunciation",
                    "Phonemes": [
                        {"Phoneme": "k", "AccuracyScore": 60.0},
                        {"Phoneme": "e", "AccuracyScore": 40.2},
                    ],
                },
            ],
        }
    ],
}


def test_parse_azure_response_maps_scores_and_words() -> None:
    result = speech.parse_azure_response(AZURE_PAYLOAD)
    assert result["provider"] == "azure"
    assert result["accuracy"] == 82
    assert result["fluency"] == 91
    assert result["completeness"] == 100
    assert result["pron"] == 87
    assert result["recognized_text"] == "朝の検温の時間です。"
    assert result["words"][0] == {
        "word": "朝",
        "accuracy": 95,
        "error_type": "None",
        "phonemes": [{"phoneme": "a", "accuracy": 96}],
    }
    weak = speech.extract_weak_words(result)
    assert weak == [{"word": "検温", "accuracy": 49}]


def test_parse_azure_response_nested_sdk_shape() -> None:
    payload = {
        "RecognitionStatus": "Success",
        "NBest": [
            {
                "AccuracyScore": 70.0,
                "FluencyScore": 70.0,
                "CompletenessScore": 100.0,
                "PronScore": 75.0,
                "Display": "テスト。",
                "Words": [
                    {
                        "Word": "テスト",
                        "PronunciationAssessment": {"AccuracyScore": 66.0},
                        "ErrorType": "None",
                        "Phonemes": [
                            {
                                "Phoneme": "t",
                                "PronunciationAssessment": {"AccuracyScore": 50.0},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = speech.parse_azure_response(payload)
    assert result["words"][0]["accuracy"] == 66
    assert result["words"][0]["phonemes"][0]["accuracy"] == 50


@pytest.mark.parametrize("status_", ["NoMatch", "InitialSilenceTimeout", "BabbleTimeout"])
def test_parse_azure_response_no_speech(status_: str) -> None:
    with pytest.raises(speech.NoSpeechRecognizedError):
        speech.parse_azure_response({"RecognitionStatus": status_})


def test_parse_azure_response_error_status() -> None:
    with pytest.raises(speech.SpeechProviderError):
        speech.parse_azure_response({"RecognitionStatus": "Error"})


def test_scores_are_clamped_to_0_100() -> None:
    assert speech._score(123.4) == 100
    assert speech._score(-5) == 0
    assert speech._score(None) == 0
    assert speech._score(82.6) == 83
