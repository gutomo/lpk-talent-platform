"""発音評価サービス。

provider_mode=stub: 資格情報不要の決定的モック（同じ入力なら同じスコア）。
provider_mode=azure: Azure AI Speech Pronunciation Assessment（REST short audio, ja-JP）。

地雷（CLAUDE.md）: prosody は ja-JP 非対応（en-US 限定）のため EnableProsodyAssessment は
送らず、accuracy / fluency / completeness + 単語・音素スコアのみ使う。
音声は 30 秒以内・WAV 16kHz mono を前提とする。
"""

import base64
import hashlib
import json
import re
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.services.audio import to_wav_16k_mono

# この値未満の accuracy、または誤読・脱落と判定された語を弱点語として集計する。
WEAK_WORD_THRESHOLD = 70

_AZURE_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_PA_PARAMS = {
    "GradingSystem": "HundredMark",
    "Granularity": "Phoneme",
    "Dimension": "Comprehensive",
    "EnableMiscue": "True",
}


class NoSpeechRecognizedError(Exception):
    """音声から発話を認識できなかった（無音・雑音・言語不一致など）。"""


class SpeechProviderError(Exception):
    """外部プロバイダ呼び出しの失敗（設定不備・ネットワーク・HTTPエラー）。"""


def _score(value: Any) -> int:
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return 0


def assess_pronunciation(audio_bytes: bytes, reference_text: str) -> dict[str, Any]:
    """アップロード音声（WebM/Opus 等）を評価し、scores jsonb 形式の dict を返す。"""
    settings = get_settings()
    if settings.provider_mode == "azure":
        wav = to_wav_16k_mono(audio_bytes)
        return assess_azure(wav, reference_text, settings)
    return assess_stub(audio_bytes, reference_text)


def extract_weak_words(result: dict[str, Any]) -> list[dict[str, Any]]:
    """weak_words jsonb（[{word, accuracy}]）を評価結果から抽出する。"""
    weak: dict[str, int] = {}
    for word in result["words"]:
        if word["error_type"] == "Insertion":
            # 参照文に無い挿入語は弱点語の対象外。
            continue
        if (
            word["error_type"] in ("Mispronunciation", "Omission")
            or word["accuracy"] < WEAK_WORD_THRESHOLD
        ):
            prev = weak.get(word["word"])
            if prev is None or word["accuracy"] < prev:
                weak[word["word"]] = word["accuracy"]
    return [{"word": w, "accuracy": a} for w, a in weak.items()]


# ---------------------------------------------------------------- stub provider

_STUB_SPLIT = re.compile(r"[、。！？!?，．・\s]+")


def _stub_tokens(reference_text: str) -> list[str]:
    """句読点で区切ったうえで 2〜3 文字の擬似「単語」に分割する（表示検証用）。"""
    tokens: list[str] = []
    for segment in _STUB_SPLIT.split(reference_text):
        i = 0
        while i < len(segment):
            size = 3 if len(segment) - i >= 3 else len(segment) - i
            tokens.append(segment[i : i + size])
            i += size
    return [t for t in tokens if t]


def assess_stub(audio_bytes: bytes, reference_text: str) -> dict[str, Any]:
    seed = hashlib.sha256(audio_bytes + reference_text.encode()).hexdigest()
    base = 62 + int(seed[:8], 16) % 28  # 62〜89

    words = []
    for i, token in enumerate(_stub_tokens(reference_text)):
        h = int(hashlib.sha256(f"{seed}:{i}:{token}".encode()).hexdigest()[:8], 16)
        accuracy = _score(base + h % 23 - 12)  # base-12 〜 base+10
        words.append(
            {
                "word": token,
                "accuracy": accuracy,
                "error_type": "Mispronunciation" if accuracy < WEAK_WORD_THRESHOLD - 10 else "None",
                "phonemes": [],
            }
        )

    accuracy = _score(sum(w["accuracy"] for w in words) / len(words)) if words else 0
    fluency = _score(base + int(seed[8:12], 16) % 9 - 4)
    completeness = _score(accuracy + int(seed[12:14], 16) % 8)
    return {
        "provider": "stub",
        "accuracy": accuracy,
        "fluency": fluency,
        "completeness": completeness,
        "pron": _score(accuracy * 0.6 + fluency * 0.2 + completeness * 0.2),
        "recognized_text": reference_text,
        "words": words,
    }


# --------------------------------------------------------------- azure provider


def build_pa_header(reference_text: str) -> str:
    """Pronunciation-Assessment ヘッダ（base64 JSON）。prosody は含めない。"""
    params = {"ReferenceText": reference_text, **_PA_PARAMS}
    return base64.b64encode(json.dumps(params, ensure_ascii=False).encode()).decode()


def stt_url(settings: Settings) -> str:
    if settings.azure_speech_endpoint:
        base = settings.azure_speech_endpoint.rstrip("/")
        return f"{base}/stt/speech/recognition/conversation/cognitiveservices/v1"
    region = settings.azure_speech_region
    return f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"


def _accuracy_of(obj: dict[str, Any]) -> int:
    # REST short audio はフラット（AccuracyScore 直下）、SDK 系 JSON はネスト。両対応。
    if "AccuracyScore" in obj:
        return _score(obj["AccuracyScore"])
    return _score(obj.get("PronunciationAssessment", {}).get("AccuracyScore"))


def parse_azure_response(payload: dict[str, Any]) -> dict[str, Any]:
    status_ = payload.get("RecognitionStatus")
    if status_ in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout"):
        raise NoSpeechRecognizedError(str(status_))
    if status_ != "Success":
        raise SpeechProviderError(f"RecognitionStatus={status_}")
    nbest = payload.get("NBest") or []
    if not nbest:
        raise NoSpeechRecognizedError("NBest が空です")
    best = nbest[0]

    words = [
        {
            "word": w.get("Word", ""),
            "accuracy": _accuracy_of(w),
            "error_type": w.get("ErrorType", "None"),
            "phonemes": [
                {"phoneme": p.get("Phoneme", ""), "accuracy": _accuracy_of(p)}
                for p in w.get("Phonemes") or []
            ],
        }
        for w in best.get("Words") or []
    ]
    return {
        "provider": "azure",
        "accuracy": _score(best.get("AccuracyScore")),
        "fluency": _score(best.get("FluencyScore")),
        "completeness": _score(best.get("CompletenessScore")),
        "pron": _score(best.get("PronScore")),
        "recognized_text": best.get("Display") or payload.get("DisplayText") or "",
        "words": words,
    }


def assess_azure(
    wav_bytes: bytes, reference_text: str, settings: Settings
) -> dict[str, Any]:
    if not settings.azure_speech_key:
        raise SpeechProviderError(
            "AZURE_SPEECH_KEY が未設定です。provider_mode=azure には資格情報が必要です。"
        )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
        "Pronunciation-Assessment": build_pa_header(reference_text),
    }
    try:
        resp = httpx.post(
            stt_url(settings),
            params={"language": "ja-JP", "format": "detailed"},
            headers=headers,
            content=wav_bytes,
            timeout=_AZURE_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SpeechProviderError(f"Azure Speech へ接続できません: {exc}") from exc
    if resp.status_code != 200:
        raise SpeechProviderError(f"Azure Speech HTTP {resp.status_code}: {resp.text[:200]}")
    return parse_azure_response(resp.json())
