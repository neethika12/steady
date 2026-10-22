"""Groq adapter: a hosted model through Groq's OpenAI-compatible API (plain HTTP, no SDK).

Used on hosted servers that can't run a local model. Only the prompt for the current request is
sent, and only when someone presses an AI button. Groq doesn't keep API data by default and
doesn't train on it (https://console.groq.com/docs/your-data). Prompts and replies aren't logged here.
"""

import json
import threading
import time
from typing import Any

import httpx

from app.ai.provider import AIBadOutput, AIUnavailable

API = "https://api.groq.com/openai/v1"
# Size and length rules are checked by the app's own validation after the reply; strict
# structured output only needs the shape (types, required fields, enums, no extra fields).
_DROP = {"minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"}


def strict_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: strict_schema(v) for k, v in schema.items() if k not in _DROP}
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


class GroqProvider:
    name = "groq"
    serial = False  # a hosted service handles several requests at once

    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout_seconds
        self._status: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def status(self) -> dict[str, Any]:
        if not self.api_key:
            return {"available": False, "reason": "not_configured",
                    "message": "AI isn't set up on this server yet (no GROQ_API_KEY)."}
        with self._lock:  # checked at most every 10 minutes per server instance
            if self._status and time.monotonic() - self._status[0] < 600:
                return self._status[1]
        try:
            r = httpx.get(f"{API}/models", headers=self._headers(), timeout=5)
        except httpx.HTTPError:
            return {"available": False, "reason": "server_unreachable", "message": "The AI service can't be reached right now."}
        if r.status_code == 401:
            result = {"available": False, "reason": "error", "message": "The AI service rejected this server's API key."}
        elif r.status_code >= 400:
            result = {"available": False, "reason": "error", "message": f"The AI service returned an error (HTTP {r.status_code})."}
        elif self.model not in {m.get("id") for m in r.json().get("data", [])}:
            result = {"available": False, "reason": "model_missing", "message": f"The AI model '{self.model}' isn't available."}
        else:
            result = {"available": True, "reason": None, "message": "AI is ready."}
        with self._lock:
            self._status = (time.monotonic(), result)
        return result

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        if not self.api_key:
            raise AIUnavailable("not_configured", "AI isn't set up on this server yet.")
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "strict": True, "schema": strict_schema(schema)}},
            "temperature": 0.2,
            # Reasoning models think before answering; keep it short and leave room for the answer.
            "reasoning_effort": "low",
            "max_completion_tokens": max_tokens + 1500,
        }
        try:
            r = httpx.post(f"{API}/chat/completions", json=body, headers=self._headers(), timeout=self.timeout)
        except httpx.TimeoutException:
            raise AIUnavailable("timeout", "The AI service took too long to answer. Try again.")
        except httpx.HTTPError:
            raise AIUnavailable("server_unreachable", "The AI service can't be reached right now.")
        if r.status_code == 429:
            raise AIUnavailable("busy", "The free AI allowance is used up for now. Try again later.")
        if r.status_code == 401:
            raise AIUnavailable("error", "The AI service rejected this server's API key.")
        if r.status_code >= 400:
            raise AIBadOutput(f"The AI service couldn't produce an answer in the required format (HTTP {r.status_code}).")
        choice = (r.json().get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise AIBadOutput("The answer was cut off at the output limit.")
        content = (choice.get("message") or {}).get("content") or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raise AIBadOutput("The answer wasn't valid JSON.")
        if not isinstance(parsed, dict):
            raise AIBadOutput("The answer wasn't a JSON object.")
        return parsed
