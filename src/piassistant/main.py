import asyncio
import sys

import uvicorn

from .config import Settings
from .services.base import ServiceRegistry
from .services.cache import CacheService
from .services.llm import LLMService
from .services.weather import WeatherService
from .services.news import NewsService
from .services.storage import StorageService
from .services.grocery import GroceryService
from .services.timers import TimerService
from .services.reminders import ReminderService
from .services.todo import TodoService
from .services.orders import AmazonOrdersService
from .services.quote import QuoteService
from .services.sysmon import SystemMonitorService
from .services.network import NetworkService
from .services.calendar import CalendarService
from .brain.agent import Agent
from .api.app import create_app


def run_server():
    settings = Settings()

    # Build services
    cache = CacheService()
    llm = LLMService(settings)
    weather = WeatherService(settings, cache)
    news = NewsService(settings, cache)
    storage = StorageService(settings)
    grocery = GroceryService(storage)
    timers = TimerService()
    reminders = ReminderService(storage)
    todo = TodoService(storage)
    orders = AmazonOrdersService(storage, settings)
    quote = QuoteService(storage, cache, settings)
    sysmon = SystemMonitorService(cache)
    network = NetworkService(storage)
    calendar = CalendarService(cache, settings)

    # Register
    registry = ServiceRegistry()
    registry.register(cache)
    registry.register(llm)
    registry.register(weather)
    registry.register(news)
    registry.register(storage)
    registry.register(grocery)
    registry.register(timers)
    registry.register(reminders)
    registry.register(todo)
    registry.register(orders)
    registry.register(quote)
    registry.register(sysmon)
    registry.register(network)
    registry.register(calendar)

    # Brain
    agent = Agent(llm, registry, settings)

    # App
    app = create_app(registry, agent, settings)

    uvicorn.run(app, host=settings.host, port=settings.port)


def run_cli():
    from .cli.repl import repl
    # Optional: python -m piassistant cli http://piassistant-mothership.local:8000
    url = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(repl(base_url=url))


def run_auth_google():
    """One-time Google Calendar OAuth2 flow. Run on a machine with a browser."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from pathlib import Path
    import json

    settings = Settings()
    creds_path = settings.google_calendar_credentials_json
    token_path = settings.google_calendar_token_path

    if not creds_path:
        print("Set GOOGLE_CALENDAR_CREDENTIALS_JSON in .env to your OAuth client JSON file path.")
        return

    scopes = ["https://www.googleapis.com/auth/calendar"]
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
    creds = flow.run_local_server(port=0)

    Path(token_path).parent.mkdir(parents=True, exist_ok=True)
    Path(token_path).write_text(creds.to_json())
    print(f"Token saved to {token_path}")
    print("Copy this file to the Pi: scp data/google_token.json akshay@piassistant-mothership.local:~/PiAssistant/data/")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        run_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "auth-google":
        run_auth_google()
    else:
        run_server()
