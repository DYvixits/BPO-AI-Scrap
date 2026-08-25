from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels up
_REPO_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://bpo:bpo@postgres:5432/bpo_ai_scrap"
    redis_url: str = "redis://redis:6379/0"

    secret_key: str = "change-me-dev-only-not-a-real-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: str = "http://localhost:5173"

    crawler_user_agent: str = "BPOAIScrapBot/0.1 (+https://github.com/DYvixits/bpo-ai-scrap)"
    crawler_max_response_bytes: int = 10 * 1024 * 1024
    crawler_request_timeout_seconds: float = 15.0
    crawler_max_concurrency: int = 8

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.secret_key == "change-me-dev-only-not-a-real-secret":
        raise RuntimeError(
            "SECRET_KEY must be overridden in production — refusing to start with the "
            "example placeholder value."
        )
    return settings
