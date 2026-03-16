import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from piassistant.brain.agent import Agent
from piassistant.brain.tools import TOOL_DEFINITIONS
from piassistant.config import Settings
from piassistant.services.base import ServiceRegistry
from piassistant.services.cache import CacheService
from piassistant.services.llm import LLMService


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
    """Create a mock Claude response with text content."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


def make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tool_123"):
    """Create a mock Claude response with tool_use."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_id
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    return response


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
