"""The provider interface. Swap Ollama for another local or hosted model by writing
another class with these two methods; nothing else in the app needs to change."""

from typing import Any, Protocol


class AIUnavailable(Exception):
    """The model can't be reached or isn't installed. Core features keep working."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason  # server_unreachable | model_missing | timeout | error
        self.message = message


class AIBadOutput(Exception):
    """The model answered, but not with usable JSON."""


class AIProvider(Protocol):
    name: str
    model: str

    def status(self) -> dict[str, Any]:
        """{"available": bool, "reason": str | None, "message": str}"""

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any],
                      max_tokens: int) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object constrained by ``schema``."""
