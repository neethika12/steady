"""Ollama adapter: plain HTTP calls to a local Ollama server (no SDK, no LangChain).

Only the prompt for the current request is sent. Prompts and replies are never logged.
"""

import json
from typing import Any

import httpx

from app.ai.provider import AIBadOutput, AIUnavailable


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout_seconds

    def _installed(self, tags: dict) -> bool:
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        return wanted in names or self.model in names

    def status(self) -> dict[str, Any]:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3)
            r.raise_for_status()
        except httpx.HTTPError:
            return {"available": False, "reason": "server_unreachable",
                    "message": f"Ollama isn't reachable at {self.base_url}."}
        if not self._installed(r.json()):
            return {"available": False, "reason": "model_missing",
                    "message": f"Ollama is running, but the model '{self.model}' isn't installed."}
        return {"available": True, "reason": None, "message": "Local AI is ready."}

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any],
                      max_tokens: int) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,  # Ollama constrains the output to this JSON schema
            "options": {"temperature": 0.2, "num_predict": max_tokens, "num_ctx": 4096},
            "keep_alive": "10m",
        }
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except httpx.TimeoutException:
            raise AIUnavailable("timeout", "The local model took too long to answer. Try again, or use a smaller request.")
        except httpx.HTTPError:
            raise AIUnavailable("server_unreachable", f"Ollama isn't reachable at {self.base_url}.")
        if r.status_code == 404:
            raise AIUnavailable("model_missing", f"The model '{self.model}' isn't installed in Ollama.")
        if r.status_code >= 400:
            raise AIUnavailable("error", f"Ollama returned an error (HTTP {r.status_code}).")
        data = r.json()
        if data.get("done_reason") == "length":
            raise AIBadOutput("The answer was cut off at the output limit.")
        content = (data.get("message") or {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raise AIBadOutput("The answer wasn't valid JSON.")
        if not isinstance(parsed, dict):
            raise AIBadOutput("The answer wasn't a JSON object.")
        return parsed
