from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import Settings
from ..services.base import ServiceRegistry
from ..services.llm import LLMService
from ..services.weather import WeatherService
from ..services.news import NewsService
from ..services.grocery import GroceryService
from ..services.timers import TimerService
from ..services.reminders import ReminderService
from ..services.todo import TodoService
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
            f"You are {self.settings.assistant_name}, a smart home assistant running on a Raspberry Pi 5.\n"
            f"You help with weather, news, grocery lists, timers, reminders, notes, to-dos, and general questions.\n\n"
            f"TOOLS: Use your tools for real-time data and persistent actions. Do NOT guess — use the tool.\n\n"
            f"GROCERY STORES: Default stores are Whole Foods, Sprouts, Indian Grocery, Costco, Target, Other.\n"
            f"If the user doesn't specify a store, ask which store, or use 'Other' if they want it generic.\n"
            f"When adding multiple items, call grocery_add once per item.\n\n"
            f"TIMERS: Convert user's time to seconds (e.g. '12 minutes' = 720 seconds).\n"
            f"REMINDERS: Convert relative times to ISO format (e.g. 'tomorrow 10am' → actual date).\n"
            f"NOTES: Use for 'remember that...', 'note that...', or when user wants to save info.\n"
            f"TO-DOS: Use for task management, action items, things to do.\n\n"
            f"FREE CAPABILITIES (no tools needed — answer directly):\n"
            f"- Unit conversions, cooking measurements\n"
            f"- Recipe suggestions from ingredients\n"
            f"- Quick math and calculations\n"
            f"- General knowledge questions\n\n"
            f"DAILY BRIEF: If asked for a daily brief/summary, chain weather + reminders + grocery tools.\n\n"
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
        # --- Weather ---
        if name == "get_current_weather":
            weather: WeatherService = self.registry.get("weather")
            return await weather.get_current(location=args.get("location", self.settings.default_location))

        elif name == "get_weather_forecast":
            weather: WeatherService = self.registry.get("weather")
            return await weather.get_forecast(
                location=args.get("location", self.settings.default_location),
                days=args.get("days", 3),
            )

        # --- News ---
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

        # --- Grocery ---
        elif name == "grocery_add":
            grocery: GroceryService = self.registry.get("grocery")
            return await grocery.add_item(
                store=args["store"],
                item=args["item"],
                quantity=args.get("quantity", ""),
            )

        elif name == "grocery_list":
            grocery: GroceryService = self.registry.get("grocery")
            return await grocery.get_list(store=args.get("store"))

        elif name == "grocery_remove":
            grocery: GroceryService = self.registry.get("grocery")
            removed = await grocery.remove_item(args["item_id"])
            return {"removed": removed}

        elif name == "grocery_clear":
            grocery: GroceryService = self.registry.get("grocery")
            count = await grocery.clear_done(store=args.get("store"))
            return {"cleared": count}

        # --- Timers ---
        elif name == "timer_set":
            timers: TimerService = self.registry.get("timers")
            return await timers.set_timer(name=args["name"], seconds=args["seconds"])

        elif name == "timer_list":
            timers: TimerService = self.registry.get("timers")
            return await timers.list_timers()

        elif name == "timer_cancel":
            timers: TimerService = self.registry.get("timers")
            cancelled = await timers.cancel_timer(args["name"])
            return {"cancelled": cancelled}

        # --- Reminders ---
        elif name == "reminder_add":
            reminders: ReminderService = self.registry.get("reminders")
            return await reminders.add_reminder(
                text=args["text"],
                due_at=args.get("due_at", ""),
                for_person=args.get("for_person", ""),
            )

        elif name == "reminder_list":
            reminders: ReminderService = self.registry.get("reminders")
            return await reminders.list_reminders()

        # --- Notes ---
        elif name == "note_add":
            reminders: ReminderService = self.registry.get("reminders")
            return await reminders.add_note(
                text=args["text"],
                for_person=args.get("for_person", ""),
                pinned=args.get("pinned", False),
            )

        elif name == "note_list":
            reminders: ReminderService = self.registry.get("reminders")
            return await reminders.list_notes()

        # --- To-Do ---
        elif name == "todo_add":
            todo: TodoService = self.registry.get("todo")
            return await todo.add_item(
                text=args["text"],
                priority=args.get("priority", ""),
            )

        elif name == "todo_list":
            todo: TodoService = self.registry.get("todo")
            return await todo.get_list()

        elif name == "todo_complete":
            todo: TodoService = self.registry.get("todo")
            completed = await todo.complete_item(args["item_id"])
            return {"completed": completed}

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
