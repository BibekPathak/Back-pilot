"""Application settings, loaded from environment /.env.

All secrets live in environment variables only; nothing is hardcoded and no
key is ever logged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the repo-root .env so the backend works both under Docker (env vars
# injected by compose) and from a local checkout where .env sits at the root.
# config.py is backend/app/config.py -> parents[2] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"), extra="ignore"
    )

    # Database
    database_url: str = "postgresql+psycopg2://backpilot:backpilot@postgres:5432/backpilot"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # Agent limits
    max_action_retries: int = 3
    max_recovery_attempts: int = 2
    agent_max_steps: int = 100
    http_timeout_ms: int = 10_000

    # HITL / dashboard
    dashboard_base_url: str = "http://localhost:3001"

    # Portal
    legacy_portal_url: str = "http://legacy-portal:8081"

    # Domain allowlist for the browser executor (demo mode). Comma separated.
    allowed_domains: str = "localhost,legacy-portal"

    # LLM planner (empty key => deterministic MockPlanner)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # Upload guardrails
    max_upload_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
