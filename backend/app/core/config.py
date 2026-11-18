from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Application settings loaded from environment / .env.

    Pydantic-settings v2 reads `.env` at repo root when running from backend/
    because we pass `env_file="../../.env"`? No — see note below. We rely on
    the process CWD being `backend/` and the .env being at the repo root.
    The safest, explicit approach: put `.env` at repo root and run uvicorn
    from `backend/` with env vars already exported, OR run uvicorn from the
    repo root. We choose: run from repo root, so `.env` is at `./.env`.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- App ----
    APP_NAME: str = "blog"
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # ---- Security ----
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- Postgres ----
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: PostgresDsn

    # ---- Redis ----
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB_CELERY_BROKER: int = 0
    REDIS_DB_CELERY_RESULTS: int = 1
    REDIS_DB_CACHE: int = 2
    REDIS_URL_BROKER: RedisDsn
    REDIS_URL_RESULTS: RedisDsn
    REDIS_URL_CACHE: RedisDsn

    # ---- MinIO ----
    MINIO_ENDPOINT: str
    MINIO_PUBLIC_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_MEDIA: str = "media"
    MINIO_REGION: str = "us-east-1"
    MINIO_USE_SSL: bool = False

    # ---- Ollama ----
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_SMALL: str = "qwen2:1.5b"
    OLLAMA_MODEL_LARGE: str = "qwen2:7b"

    # ---- Observability ----
    METRICS_ENABLED: bool = True

    @field_validator("DATABASE_URL")
    @classmethod
    def _require_async_driver(cls, v: PostgresDsn) -> PostgresDsn:
        if "+asyncpg" not in str(v):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg://")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
