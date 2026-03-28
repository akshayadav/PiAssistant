import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from piassistant.brain.agent import Agent
from piassistant.brain.tools import TOOL_DEFINITIONS
from piassistant.config import Settings
from piassistant.services.base import ServiceRegistry
from piassistant.services.cache import CacheService
from piassistant.services.llm import LLMService, LLMResponse, TextBlock, ToolUseBlock


@pytest.fixture
def settings():
    return Settings(
        anthropic_api_key="test-key",
        newsapi_key="test-key",
    )


@pytest.fixture
def registry(settings):
    cache = CacheService()
    reg = ServiceRegistry()
    reg.register(cache)
    return reg


def make_text_response(text: str):
    """Create a mock response with text content."""
    return LLMResponse(content=[TextBlock(text=text)], stop_reason="end_turn")


def make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tool_123"):
    """Create a mock response with tool_use."""
    return LLMResponse(
        content=[ToolUseBlock(id=tool_id, name=tool_name, input=tool_input)],
        stop_reason="tool_use",
    )


class TestAgent:
    @pytest.mark.asyncio
    async def test_simple_text_response(self, settings, registry):
        llm = MagicMock(spec=LLMService)
        llm.chat = AsyncMock(return_value=make_text_response("Hello there!"))

        agent = Agent(llm, registry, settings)
        result = await agent.process("Hi")
        assert result == "Hello there!"
        assert len(agent.conversation) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_reset_clears_history(self, settings, registry):
        llm = MagicMock(spec=LLMService)
        llm.chat = AsyncMock(return_value=make_text_response("Hi"))

        agent = Agent(llm, registry, settings)
        await agent.process("Hello")
        assert len(agent.conversation) > 0
        agent.reset()
        assert len(agent.conversation) == 0

    def test_tool_definitions_are_valid(self):
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
