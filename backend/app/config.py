"""Configuration read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Config:
    database_url: str
    default_timezone: str
    ollama_base_url: str
    ollama_model: str
    ai_timeout_seconds: float
    ai_max_output_tokens: int
    ai_max_retries: int
    ai_requests_per_minute: int
    cors_origins: tuple[str, ...]
    cookie_secure: bool
    signup_enabled: bool
    claim_existing_data: bool
    session_days: int
    ai_enabled: bool
    ai_provider: str
    groq_api_key: str
    groq_model: str
    ai_daily_limit_per_user: int
    migrate_on_start: bool


def _flag(value: str | None, default: bool) -> bool:
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def _database_url(url: str) -> str:
    # Hosts such as Railway hand out "postgres://" or "postgresql://" URLs; this app uses psycopg 3.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_config() -> Config:
    env = os.environ
    return Config(
        database_url=_database_url(env.get(
            "DATABASE_URL", "postgresql+psycopg://steady:steady_local_only@localhost:5432/steady"
        )),
        default_timezone=env.get("DEFAULT_TIMEZONE", "UTC"),
        ollama_base_url=env.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=env.get("OLLAMA_MODEL", "phi4-mini"),
        ai_timeout_seconds=float(env.get("AI_TIMEOUT_SECONDS", "120")),
        ai_max_output_tokens=int(env.get("AI_MAX_OUTPUT_TOKENS", "700")),
        ai_max_retries=int(env.get("AI_MAX_RETRIES", "1")),
        ai_requests_per_minute=int(env.get("AI_REQUESTS_PER_MINUTE", "6")),
        # Only needed when running the Vite dev server outside Docker.
        cors_origins=tuple(
            o.strip()
            for o in env.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        ),
        # Session cookies are sent over HTTPS only. Set COOKIE_SECURE=false only for plain-http local use.
        cookie_secure=_flag(env.get("COOKIE_SECURE"), True),
        signup_enabled=_flag(env.get("SIGNUP_ENABLED"), True),
        # Local only: the first account created takes over data from before accounts existed.
        claim_existing_data=_flag(env.get("CLAIM_EXISTING_DATA"), False),
        session_days=int(env.get("SESSION_DAYS", "30")),
        # Hosted servers usually can't run a local model; AI_ENABLED=false hides the AI features.
        ai_enabled=_flag(env.get("AI_ENABLED"), True),
        # "ollama" (a model on this computer) or "groq" (hosted; needs GROQ_API_KEY).
        ai_provider=env.get("AI_PROVIDER", "ollama").strip().lower(),
        groq_api_key=env.get("GROQ_API_KEY", "").strip(),
        groq_model=env.get("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        # AI requests each person may make per 24 hours (0 = no limit, the default locally).
        ai_daily_limit_per_user=int(env.get("AI_DAILY_LIMIT_PER_USER", "0")),
        # Serverless hosts have no start script: apply pending migrations on the first request.
        migrate_on_start=_flag(env.get("MIGRATE_ON_START"), False),
    )
