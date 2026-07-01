from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "GitHub Analytics API"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"

    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    DATABASE_URL: str

    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    PASSWORD_MIN_LENGTH: int = 8

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    REPOS_BASE_PATH: str = "./data/repos"
    ANALYTICS_CACHE_TTL_SECONDS: int = 300
    GIT_CLONE_TIMEOUT_SECONDS: int = 600
    PARSE_BATCH_SIZE: int = 500
    PARSE_USE_GIT_LOG: bool = True
    ANALYSIS_MAX_COMMITS: int = 0
    INACTIVE_CONTRIBUTOR_DAYS: int = 90
    JOB_POLL_TIMEOUT_SECONDS: int = 240

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if value == "change-me-to-a-long-random-secret":
            raise ValueError(
                "SECRET_KEY must be set to a secure random value. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            import json

            return json.loads(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
