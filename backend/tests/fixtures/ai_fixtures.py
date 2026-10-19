"""TEST FIXTURES ONLY. These canned replies stand in for a model during automated
tests. They are never used by the running app and are not real AI output."""

from app.ai.provider import AIBadOutput, AIUnavailable


class FixtureProvider:
    """Returns pre-written replies in order and records every prompt it receives."""

    name = "test-fixture"
    model = "fixture (not a real model)"

    def __init__(self, replies=None, available=True):
        self.replies = list(replies or [])
        self.prompts: list[str] = []
        self.available = available

    def status(self):
        if not self.available:
            return {"available": False, "reason": "server_unreachable", "message": "fixture: offline"}
        return {"available": True, "reason": None, "message": "fixture"}

    def generate_json(self, *, system, prompt, schema, max_tokens):
        self.prompts.append(prompt)
        if not self.available:
            raise AIUnavailable("server_unreachable", "fixture: offline")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


BAD_JSON = AIBadOutput("The answer wasn't valid JSON.")
