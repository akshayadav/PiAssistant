from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import Settings
from ..services.base import ServiceRegistry
from ..services.llm import LLMService
from ..services.weather import WeatherService
from ..services.news import NewsService
from .tools import TOOL_DEFINITIONS


class Agent:
    """Claude-powered agent that routes natural language to services via tool use."""

    def __init__(self, llm: LLMService, registry: ServiceRegistry, settings: Settings):
        self.llm = llm
        self.registry = registry
        self.settings = settings
        self.conversation: list[dict] = []
        self.max_history = 40

    async def process(self, user_message: str) -> str:
        """Process user input. Runs tool-use loop until Claude produces a text response."""
        self.conversation.append({"role": "user", "content": user_message})
        self._trim_history()

        while True:
            response = await self.llm.chat(
                messages=self.conversation,
                system=self._system_prompt(),
                tools=TOOL_DEFINITIONS,
            )

            self.conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            if response.stop_reason == "tool_use":
                tool_results = await self._execute_tools(response)
                self.conversation.append({"role": "user", "content": tool_results})
                continue

            return self._extract_text(response)

    def reset(self) -> None:
        """Clear conversation history."""
        self.conversation.clear()

    def _system_prompt(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"You are {self.settings.assistant_name}, a smart assistant running on a Raspberry Pi 5. "
            f"You help with weather, news, and general questions. You have access to tools for real-time data.\n\n"
            f"When the user asks about weather or news, USE YOUR TOOLS rather than relying on training data.\n"
            f"Keep responses concise and conversational.\n"
            f"Current time: {now}\n"
            f"Default location: {self.settings.default_location}"
        )

    async def _execute_tools(self, response) -> list[dict]:
        results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = await self._dispatch_tool(block.name, block.input)
                    content = json.dumps(result)
                except Exception as e:
                    content = json.dumps({"error": str(e)})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                })
        return results

    async def _dispatch_tool(self, name: str, args: dict) -> dict | list:
        if name == "get_current_weather":
            weather: WeatherService = self.registry.get("weather")
            return await weather.get_current(location=args.get("location", self.settings.default_location))

        elif name == "get_weather_forecast":
            weather: WeatherService = self.registry.get("weather")
            return await weather.get_forecast(
                location=args.get("location", self.settings.default_location),
                days=args.get("days", 3),
            )

        elif name == "get_news_headlines":
            news: NewsService = self.registry.get("news")
            return await news.get_headlines(
                category=args.get("category", "general"),
                count=args.get("count", 5),
            )

        elif name == "search_news":
            news: NewsService = self.registry.get("news")
            return await news.search(
                query=args["query"],
                count=args.get("count", 5),
            )

        else:
            return {"error": f"Unknown tool: {name}"}

    def _extract_text(self, response) -> str:
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts) if parts else "I'm not sure how to respond to that."

    def _trim_history(self) -> None:
        if len(self.conversation) > self.max_history:
            self.conversation = self.conversation[-self.max_history:]
