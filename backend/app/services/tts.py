"""音声合成サービス（Azure Neural TTS, ja-JP）。

provider_mode=stub: 音声を生成しない（None を返す）。フロントは browser の
speechSynthesis(ja-JP) で面接官の発話を読み上げる（資格情報なしでもデモが音声で通る）。
provider_mode=azure: Azure Neural TTS REST。SSML で ja-JP の声を指定し MP3 を返す。

STT と同じ Speech リソース（azure_speech_key / region / endpoint）を使う。
"""

from xml.sax.saxutils import escape

import httpx

from app.config import Settings, get_settings

_TTS_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# モバイル回線でも軽い MP3。ブラウザの <audio> でそのまま再生できる。
_TTS_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
TTS_MEDIA_TYPE = "audio/mpeg"


class TtsProviderError(Exception):
    """音声合成プロバイダ呼び出しの失敗（設定不備・ネットワーク・HTTPエラー）。"""


def build_ssml(text_ja: str, voice: str) -> str:
    """ja-JP の SSML を組み立てる。text_ja は XML エスケープする。"""
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">'
        f'<voice name="{escape(voice)}">{escape(text_ja)}</voice>'
        "</speak>"
    )


def tts_url(settings: Settings) -> str:
    if settings.azure_speech_endpoint:
        base = settings.azure_speech_endpoint.rstrip("/")
        return f"{base}/tts/cognitiveservices/v1"
    region = settings.azure_speech_region
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


def synthesize(text_ja: str) -> bytes | None:
    """面接官の発話を音声（MP3 バイト列）にする。stub モードでは None。"""
    settings = get_settings()
    if settings.provider_mode != "azure":
        return None
    return synthesize_azure(text_ja, settings)


def synthesize_azure(text_ja: str, settings: Settings) -> bytes:
    if not settings.azure_speech_key:
        raise TtsProviderError(
            "AZURE_SPEECH_KEY が未設定です。provider_mode=azure には資格情報が必要です。"
        )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": _TTS_OUTPUT_FORMAT,
        "User-Agent": "lpk-talent-platform",
    }
    ssml = build_ssml(text_ja, settings.azure_tts_voice)
    try:
        resp = httpx.post(
            tts_url(settings),
            headers=headers,
            content=ssml.encode("utf-8"),
            timeout=_TTS_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise TtsProviderError(f"Azure TTS へ接続できません: {exc}") from exc
    if resp.status_code != 200:
        raise TtsProviderError(f"Azure TTS HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.content
