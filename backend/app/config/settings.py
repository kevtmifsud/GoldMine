from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    DATA_PROVIDER: str = "csv"
    STORAGE_PROVIDER: str = "local"
    DATA_DIR: str = "../data/structured"
    STORAGE_DIR: str = "../data/unstructured"
    VIEWS_DIR: str = "../data/views"
    DOCUMENTS_DIR: str = "../data/documents"
    SCHEDULES_DIR: str = "../data/schedules"
    SCHEDULER_INTERVAL_SECONDS: int = 60
    EMAIL_MAX_ROWS_PER_WIDGET: int = 50
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    LLM_MAX_CONTEXT_CHUNKS: int = 15
    LLM_MAX_RESPONSE_TOKENS: int = 1024
    LOG_LEVEL: str = "DEBUG"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    MAX_PAGE_SIZE: int = 200
    DEFAULT_PAGE_SIZE: int = 50

    model_config = {"env_prefix": "GOLDMINE_"}


settings = Settings()
