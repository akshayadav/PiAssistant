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
        llm.backend = "anthropic"
        llm.chat = AsyncMock(return_value=make_text_response("Hello there!"))

        agent = Agent(llm, registry, settings)
        result = await agent.process("Hi")
        assert result == "Hello there!"
        assert len(agent.conversation) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_reset_clears_history(self, settings, registry):
        llm = MagicMock(spec=LLMService)
        llm.backend = "anthropic"
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


class TestToolFiltering:
    def test_weather_keywords_return_weather_tools(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("What's the weather like?")
        names = {t["name"] for t in tools}
        assert "get_current_weather" in names
        assert "get_weather_forecast" in names
        assert len(tools) == 2

    def test_grocery_keywords_return_grocery_tools(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("Add milk to the grocery list")
        names = {t["name"] for t in tools}
        assert "grocery_add" in names
        assert "grocery_list" in names
        assert len(tools) <= 10  # grocery group has 9 tools

    def test_timer_keywords_return_timer_tools(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("Set a timer for 10 minutes")
        names = {t["name"] for t in tools}
        assert "timer_set" in names
        assert len(tools) == 3

    def test_no_keywords_conversational_returns_empty(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("Thanks, that sounds great!")
        assert tools == []

    def test_no_keywords_action_returns_all(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("What can you do for me?")
        assert len(tools) == len(TOOL_DEFINITIONS)

    def test_compound_daily_brief(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("Give me a daily brief")
        names = {t["name"] for t in tools}
        assert "get_current_weather" in names
        assert "task_list" in names
        assert "get_calendar_events" in names

    def test_multiple_groups_combined(self):
        from piassistant.brain.tools import filter_tools
        tools = filter_tools("Check the weather and set a timer")
        names = {t["name"] for t in tools}
        assert "get_current_weather" in names
        assert "timer_set" in names
