from __future__ import annotations

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    DATA_PROVIDER: str = "supabase"
    STORAGE_PROVIDER: str = "local"
    DATA_DIR: str = "../data/structured"
    STORAGE_DIR: str = "../data/unstructured"
    VIEWS_DIR: str = "../data/views"
    STUDIOS_DIR: str = "../data/studios"
    DOCUMENTS_DIR: str = "../data/documents"
    SCHEDULES_DIR: str = "../data/schedules"
    SCHEDULER_INTERVAL_SECONDS: int = 60
    EMAIL_MAX_ROWS_PER_WIDGET: int = 50
    EMAIL_PROVIDER: str = "console"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_SENDER: str = ""
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    LLM_MAX_CONTEXT_CHUNKS: int = 15
    LLM_MAX_RESPONSE_TOKENS: int = 1024
    EMBEDDING_PROVIDER: str = "voyage"
    EMBEDDING_MODEL: str = "voyage-3"
    EMBEDDING_DIMENSIONS: int = 1024
    LOG_LEVEL: str = "DEBUG"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    MAX_PAGE_SIZE: int = 1000
    DEFAULT_PAGE_SIZE: int = 50

    # Supabase S3-compatible storage (for financial model Excel files)
    SUPABASE_STORAGE_URL: str = ""
    S3_BUCKET: str = "financial_model_outputs"
    S3_MODELS_PREFIX: str = "financial_model_outputs"
    AWS_REGION: str = "us-east-1"

    @property
    def aws_access_key_id(self) -> str:
        """Read from AWS_ACCESS_KEY_ID env var (standard AWS convention, no GOLDMINE_ prefix)."""
        return os.environ.get("AWS_ACCESS_KEY_ID", "")

    @property
    def aws_secret_access_key(self) -> str:
        """Read from AWS_SECRET_ACCESS_KEY env var (standard AWS convention, no GOLDMINE_ prefix)."""
        return os.environ.get("AWS_SECRET_ACCESS_KEY", "")

    model_config = {"env_prefix": "GOLDMINE_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
