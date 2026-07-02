from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://lpk:lpk@localhost:5432/lpk"
    # AI provider mode. "stub" = deterministic mocks (no external credentials).
    # Switch to "azure" / "bedrock" in later slices when credentials are wired.
    provider_mode: str = "stub"


@lru_cache
def get_settings() -> Settings:
    return Settings()
