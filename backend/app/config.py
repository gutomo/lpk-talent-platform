from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://lpk:lpk@localhost:5432/lpk"
    # AI provider mode. "stub" = deterministic mocks (no external credentials).
    # Switch to "azure" / "bedrock" in later slices when credentials are wired.
    provider_mode: str = "stub"
    # Azure AI Speech（provider_mode=azure のとき必須）。
    azure_speech_key: str = ""
    azure_speech_region: str = "japaneast"
    # カスタムサブドメイン利用時の上書き（例: https://myresource.cognitiveservices.azure.com）。
    # 空なら region ベースの STT エンドポイントを使う。
    azure_speech_endpoint: str = ""
    session_ttl_days: int = 7
    # dev は http://localhost なので False。本番（ACA、https）では True にする。
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
