from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://lpk:lpk@localhost:5432/lpk"
    # 発音評価プロバイダ。"stub" = 資格情報不要の決定的モック、"azure" = Azure AI Speech。
    provider_mode: str = "stub"
    # 会話・面接のLLMプロバイダ。"stub" | "bedrock"。発音評価の provider_mode とは独立に切り替える。
    llm_provider_mode: str = "stub"
    # llm_provider_mode=bedrock のとき使用。資格情報は boto3 の既定チェーン（環境変数等）から取る。
    aws_region: str = "ap-northeast-1"
    bedrock_model_id: str = "anthropic.claude-sonnet-4-20250514-v1:0"
    # Azure AI Speech（provider_mode=azure のとき必須）。
    azure_speech_key: str = ""
    azure_speech_region: str = "japaneast"
    # カスタムサブドメイン利用時の上書き（例: https://myresource.cognitiveservices.azure.com）。
    # 空なら region ベースの STT エンドポイントを使う。
    azure_speech_endpoint: str = ""
    # 面接官の音声合成に使う Neural TTS の声（ja-JP）。STT と同じ Speech リソースを使う。
    azure_tts_voice: str = "ja-JP-NanamiNeural"
    session_ttl_days: int = 7
    # dev は http://localhost なので False。本番（ACA、https）では True にする。
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
