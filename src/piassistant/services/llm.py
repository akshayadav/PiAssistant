from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ..config import Settings
from .base import BaseService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified response types — Agent uses these regardless of backend
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class LLMResponse:
    """Unified response that works for both Anthropic and local LLM backends."""
    content: list = field(default_factory=list)  # list of TextBlock / ToolUseBlock
    stop_reason: str = "end_turn"  # "end_turn" or "tool_use"


# ---------------------------------------------------------------------------
# Tool format converter: Anthropic → OpenAI
# ---------------------------------------------------------------------------

def anthropic_to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function-calling format."""
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


# ---------------------------------------------------------------------------
# LLMService
# ---------------------------------------------------------------------------

class LLMService(BaseService):
    """LLM wrapper supporting Anthropic API and local LLM (LM Studio / Ollama)."""

    name = "llm"

    def __init__(self, settings: Settings):
        self.backend = settings.llm_backend  # "anthropic" or "local"
        self.settings = settings

        if self.backend == "anthropic":
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            self.model = settings.claude_model
        else:
            self.base_url = settings.lmstudio_url.rstrip("/")
            self.model = settings.lmstudio_model
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if self.backend == "anthropic":
            return await self._chat_anthropic(messages, system, tools, max_tokens)
        return await self._chat_local(messages, system, tools, max_tokens)

    # ---- Anthropic backend ------------------------------------------------

    async def _chat_anthropic(
        self, messages, system, tools, max_tokens,
    ) -> LLMResponse:
        import anthropic

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        raw = await self.client.messages.create(**kwargs)

        # Convert native Anthropic response → unified LLMResponse
        content = []
        for block in raw.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(ToolUseBlock(id=block.id, name=block.name, input=block.input))
        return LLMResponse(content=content, stop_reason=raw.stop_reason)

    # ---- Local LLM backend (OpenAI-compatible) ----------------------------

    async def _chat_local(
        self, messages, system, tools, max_tokens,
    ) -> LLMResponse:
        # Build OpenAI-format messages
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        for msg in messages:
            converted = self._convert_message(msg)
            # _convert_message returns a list for tool_result blocks (one per tool)
            if isinstance(converted, list):
                oai_messages.extend(converted)
            else:
                oai_messages.append(converted)

        payload: dict = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if tools:
            payload["tools"] = anthropic_to_openai_tools(tools)

        logger.debug("Local LLM request: model=%s, messages=%d, tools=%d",
                      self.model, len(oai_messages), len(tools or []))

        resp = await self._http.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        content = []

        # Text content
        if message.get("content"):
            # Strip thinking tags that some models produce (e.g. Qwen3)
            text = message["content"]
            # Remove <think>...</think> blocks
            import re
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if text:
                content.append(TextBlock(text=text))

        # Tool calls
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc["function"]
                args = func.get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                content.append(ToolUseBlock(
                    id=tc.get("id", f"call_{func['name']}"),
                    name=func["name"],
                    input=args,
                ))

        # Map finish_reason to our stop_reason
        if message.get("tool_calls"):
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"

        return LLMResponse(content=content, stop_reason=stop_reason)

    def _convert_message(self, msg: dict) -> dict:
        """Convert Anthropic-format messages to OpenAI format."""
        role = msg["role"]
        content = msg.get("content", "")

        # Simple text message
        if isinstance(content, str):
            return {"role": role, "content": content}

        # Anthropic content blocks (assistant response with tool_use, or user with tool_result)
        if isinstance(content, list):
            # Assistant message with mixed text + tool_use blocks
            if role == "assistant":
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        })
                    elif isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            })
                result = {"role": "assistant", "content": "\n".join(text_parts) or None}
                if tool_calls:
                    result["tool_calls"] = tool_calls
                return result

            # User message with tool_result blocks
            if role == "user":
                tool_messages = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
                # If there are tool results, return them as separate messages
                # We handle this specially in _chat_local
                if tool_messages:
                    return tool_messages  # Will be flattened in _chat_local

        return {"role": role, "content": str(content)}

    async def health_check(self) -> dict:
        if self.backend == "anthropic":
            if not self.client.api_key:
                return {"healthy": False, "details": "No API key configured"}
            return {"healthy": True, "details": f"anthropic model={self.model}"}
        else:
            try:
                resp = await self._http.get("/v1/models")
                resp.raise_for_status()
                return {"healthy": True, "details": f"local model={self.model} at {self.base_url}"}
            except Exception as e:
                return {"healthy": False, "details": f"LM Studio unreachable: {e}"}
