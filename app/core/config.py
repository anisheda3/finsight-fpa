"""Application settings — pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:                                       # pragma: no cover
    from pydantic import BaseSettings  # type: ignore
    SettingsConfigDict = dict  # type: ignore


class Settings(BaseSettings):
    # API
    app_name: str = "FinSight FP&A AI"
    app_env: str = "dev"
    log_level: str = "INFO"

    # Datastores
    postgres_url: str = "postgresql://postgres:password@localhost:5432/finsight_fpa"
    redis_url: str = "redis://localhost:6379/0"

    # Temporal
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "finsight-fpa"

    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    llm_model: str = "gemini-1.5-flash"

    # Slack / Email
    slack_bot_token: str | None = None
    slack_hitl_channel: str = "#fpa-hitl"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_distribution_list: str = "cfo@example.com"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
