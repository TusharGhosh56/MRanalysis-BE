from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
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

    DATABASE_URL: str = "sqlite+pysqlite:///:memory:"
    SECRET_KEY: str = "default-development-secret-key-32-characters-minimum"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    PASSWORD_MIN_LENGTH: int = 8

    # Legacy Redis / Celery (Deprecated; in-process worker and in-memory cache used now)
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
    GITHUB_TOKEN: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    @field_validator(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "PASSWORD_MIN_LENGTH",
        "ANALYTICS_CACHE_TTL_SECONDS",
        "GIT_CLONE_TIMEOUT_SECONDS",
        "PARSE_BATCH_SIZE",
        "ANALYSIS_MAX_COMMITS",
        "INACTIVE_CONTRIBUTOR_DAYS",
        "JOB_POLL_TIMEOUT_SECONDS",
        mode="before",
    )
    @classmethod
    def parse_int_safe(cls, value: object, info: ValidationInfo) -> int | object:
        if isinstance(value, str):
            clean = value.strip().strip("'").strip('"')
            if not clean:
                field_info = cls.model_fields.get(info.field_name)
                return field_info.default if field_info else 0
            try:
                return int(clean)
            except ValueError:
                field_info = cls.model_fields.get(info.field_name)
                return field_info.default if field_info else 0
        return value

    @field_validator("DEBUG", "PARSE_USE_GIT_LOG", mode="before")
    @classmethod
    def parse_bool_safe(cls, value: object, info: ValidationInfo) -> bool | object:
        if isinstance(value, str):
            clean = value.strip().lower()
            if not clean:
                field_info = cls.model_fields.get(info.field_name)
                return field_info.default if field_info else False
            if clean in ("true", "1", "yes", "on"):
                return True
            if clean in ("false", "0", "no", "off"):
                return False
        return value

    @field_validator(
        "DATABASE_URL",
        "SECRET_KEY",
        "GITHUB_TOKEN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        mode="before",
    )
    @classmethod
    def clean_strings(cls, value: object, info: ValidationInfo) -> str | object:
        if isinstance(value, str):
            clean = value.strip().strip("'").strip('"')
            if not clean:
                field_info = cls.model_fields.get(info.field_name)
                return field_info.default if field_info else ""
            return clean
        return value

    @field_validator("REPOS_BASE_PATH", mode="before")
    @classmethod
    def set_repos_base_path(cls, value: object) -> str:
        # In serverless environments (Vercel, AWS Lambda), only /tmp is writable
        import os
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            return "/tmp/repos"
        if isinstance(value, str):
            clean = value.strip().strip("'").strip('"')
            if clean:
                return clean
        return "./data/repos"

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
    def parse_cors_origins(cls, value: object) -> list[str] | object:
        if isinstance(value, str):
            clean = value.strip()
            if not clean:
                return ["http://localhost:5173"]
            if clean.startswith("[") and clean.endswith("]"):
                try:
                    import json

                    parsed = json.loads(clean)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return [origin.strip() for origin in clean.split(",") if origin.strip()]
        return value



@lru_cache
def get_settings() -> Settings:
    return Settings()
