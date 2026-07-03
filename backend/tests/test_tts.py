from app.config import Settings
from app.services import tts


def test_build_ssml_escapes_and_names_voice() -> None:
    ssml = tts.build_ssml("面接<やあ> & おはよう", "ja-JP-NanamiNeural")
    assert 'name="ja-JP-NanamiNeural"' in ssml
    assert 'xml:lang="ja-JP"' in ssml
    # XML 特殊文字はエスケープする（生の < & が SSML に混ざらない）。
    assert "&lt;" in ssml and "&gt;" in ssml and "&amp;" in ssml
    assert "<やあ>" not in ssml


def test_tts_url_region_and_custom_endpoint() -> None:
    regional = Settings(azure_speech_region="japaneast", _env_file=None)
    assert tts.tts_url(regional) == (
        "https://japaneast.tts.speech.microsoft.com/cognitiveservices/v1"
    )
    custom = Settings(
        azure_speech_endpoint="https://myres.cognitiveservices.azure.com/", _env_file=None
    )
    assert tts.tts_url(custom) == (
        "https://myres.cognitiveservices.azure.com/tts/cognitiveservices/v1"
    )


def test_synthesize_returns_none_in_stub_mode(monkeypatch) -> None:
    monkeypatch.setattr(tts, "get_settings", lambda: Settings(provider_mode="stub", _env_file=None))
    assert tts.synthesize("こんにちは。") is None


def test_synthesize_azure_requires_key() -> None:
    settings = Settings(provider_mode="azure", azure_speech_key="", _env_file=None)
    try:
        tts.synthesize_azure("こんにちは。", settings)
    except tts.TtsProviderError as exc:
        assert "AZURE_SPEECH_KEY" in str(exc)
    else:
        raise AssertionError("資格情報が無ければ TtsProviderError")
