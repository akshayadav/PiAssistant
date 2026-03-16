from __future__ import annotations

import anthropic

from ..config import Settings
from .base import BaseService


class LLMService(BaseService):
    """Thin wrapper around the Anthropic SDK."""

    name = "llm"

    def __init__(self, settings: Settings):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> anthropic.types.Message:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        return await self.client.messages.create(**kwargs)

    async def health_check(self) -> dict:
        if not self.client.api_key:
            return {"healthy": False, "details": "No API key configured"}
        return {"healthy": True, "details": f"model={self.model}"}
