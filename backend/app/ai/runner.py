"""Run one AI request safely: rate limit, one-at-a-time, bounded retries, validation.

Nothing here writes to the database. Every AI result is a *proposal* that the user
must accept explicitly through the normal (non-AI) endpoints.
"""

import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.groq import GroqProvider
from app.ai.ollama import OllamaProvider
from app.ai.provider import AIBadOutput, AIProvider, AIUnavailable
from app.config import get_config
from app.errors import AppError

log = logging.getLogger("steady.ai")  # logs feature names, timings and outcomes only

T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = (
    "You are a careful planning assistant inside a personal productivity app. "
    "Use ONLY the records given in the request and refer to them by their ref (such as T1, R2, H3). "
    "Never invent records, dates, durations or numbers. "
    "Keep observations (what the records show) separate from suggestions (what the person could try). "
    "Do not diagnose or speculate about mental health, personality, character or motivation, "
    "and do not claim to know why something happened; say 'may' or 'could' when unsure. "
    "Be brief, kind, neutral and practical. Reply only with JSON that matches the given schema."
)

# Deterministic guard: reject answers that diagnose or judge the person.
_FORBIDDEN = re.compile(
    r"\b(depress(ion|ed|ive)|anxiety disorder|adhd|bipolar|ptsd|ocd|burn[- ]?out|"
    r"diagnos\w*|disorder|mental illness|lazy|laziness|unmotivated|lack of (motivation|discipline|willpower)|"
    r"procrastinator|failure as)\b",
    re.IGNORECASE,
)


class ProposalRejected(Exception):
    pass


_REF_LABEL = re.compile(r"^\s*(?:[A-Z]\d{1,2}|\d{1,2})\s*[:.)\-]\s*")
_INLINE_REFS = re.compile(r"\s*\((?:refs?|records?|habits?)\s*:?[^)]*\)", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_REF_TOKEN = re.compile(r"\b[A-Z]\d{1,2}\b")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def tidy(text: str) -> str:
    """Remove list labels like 'T1:' and inline '(refs: R1, R2)'. The app shows sources itself."""
    return _INLINE_REFS.sub("", _REF_LABEL.sub("", text)).strip()


def name_refs(text: str, names: dict[str, str]) -> str:
    """Replace any ref the model wrote into the text (e.g. 'H2') with the record's real name."""
    return _REF_TOKEN.sub(lambda m: f"“{names[m.group(0)]}”" if m.group(0) in names else m.group(0), text)


_MORE = re.compile(r"\b(increas\w*|more (often|days|frequent\w*|sessions)|every day|each day|daily)\b", re.IGNORECASE)


def asks_for_more(text: str) -> bool:
    return bool(_MORE.search(text))


def check_numbers(text: str, allowed: set[float]) -> None:
    """Every number the model states must come from the supplied, calculated data."""
    cleaned = _REF_TOKEN.sub(" ", _ISO_DATE.sub(" ", text))
    for n in _NUMBER.findall(cleaned):
        if float(n) not in allowed:
            raise ProposalRejected(f"it stated the number {n}, which is not in the supplied data")


def check_language(*texts: str) -> None:
    for t in texts:
        if _FORBIDDEN.search(t or ""):
            raise ProposalRejected("it used diagnostic or judgmental language")


class DisabledProvider:
    """Used when AI_ENABLED=false (for example on a hosted server with no local model)."""

    name = "disabled"
    model = "none"
    MESSAGE = "AI features are turned off on this server. They work when you run Steady on your own computer."

    def status(self) -> dict[str, Any]:
        return {"available": False, "reason": "disabled", "message": self.MESSAGE}

    def generate_json(self, **_: Any) -> dict[str, Any]:
        raise AIUnavailable("disabled", self.MESSAGE)


@lru_cache
def default_provider() -> AIProvider:
    cfg = get_config()
    if not cfg.ai_enabled:
        return DisabledProvider()
    if cfg.ai_provider == "groq":
        return GroqProvider(cfg.groq_api_key, cfg.groq_model, cfg.ai_timeout_seconds)
    return OllamaProvider(cfg.ollama_base_url, cfg.ollama_model, cfg.ai_timeout_seconds)


def get_provider() -> AIProvider:
    """FastAPI dependency. Tests override it with a clearly labelled fixture provider."""
    return default_provider()


class RateLimiter:
    """At most ``per_minute`` requests in any 60 seconds; one at a time for a local model."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()
        self.busy = threading.Lock()

    def acquire(self, serial: bool = True) -> None:
        with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                wait = int(60 - (now - self.calls[0])) + 1
                raise AppError(429, "ai_rate_limited",
                               f"AI request limit reached ({self.per_minute} per minute). Try again in about {wait} s.")
            if serial and not self.busy.acquire(blocking=False):
                raise AppError(429, "ai_busy", "The local model is still working on another request.")
            self.calls.append(now)

    def release(self, serial: bool = True) -> None:
        if serial:
            self.busy.release()


limiter = RateLimiter(get_config().ai_requests_per_minute)


def unavailable_error(exc: AIUnavailable) -> AppError:
    return AppError(503, "ai_unavailable", f"AI unavailable: {exc.message}", reason=exc.reason)


def run(
    provider: AIProvider,
    feature: str,
    prompt: str,
    schema: dict[str, Any],
    model_cls: type[T],
    validate: Callable[[T, bool], Any],
    max_tokens: int | None = None,
) -> Any:
    """Ask the model, validate the answer, retry a bounded number of times.

    ``validate(answer, last_attempt)`` raises ProposalRejected if the answer isn't
    acceptable, and otherwise returns the final (deterministically checked) result.
    """
    cfg = get_config()
    limit = min(max_tokens or cfg.ai_max_output_tokens, cfg.ai_max_output_tokens)
    attempts = 1 + max(0, cfg.ai_max_retries)
    serial = getattr(provider, "serial", True)  # a local model answers one request at a time
    limiter.acquire(serial)
    try:
        last_problem = ""
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            full_prompt = prompt if not last_problem else (
                f"{prompt}\n\nYour previous answer was rejected because {last_problem}. Follow the rules exactly.")
            try:
                raw = provider.generate_json(system=SYSTEM_PROMPT, prompt=full_prompt, schema=schema, max_tokens=limit)
                result = validate(model_cls.model_validate(raw), attempt == attempts)
                log.info("ai feature=%s attempt=%d outcome=ok seconds=%.1f", feature, attempt, time.monotonic() - started)
                return result
            except AIUnavailable as exc:
                log.warning("ai feature=%s attempt=%d outcome=unavailable reason=%s", feature, attempt, exc.reason)
                raise unavailable_error(exc)
            except (AIBadOutput, ValidationError, ProposalRejected) as exc:
                last_problem = (str(exc) if isinstance(exc, (AIBadOutput, ProposalRejected))
                                else "it did not match the required format")
                log.warning("ai feature=%s attempt=%d outcome=rejected kind=%s", feature, attempt, type(exc).__name__)
        raise AppError(502, "ai_invalid",
                       f"The AI's answer was rejected ({last_problem}), so nothing is shown. "
                       "You can try again; nothing was changed.")
    finally:
        limiter.release(serial)
