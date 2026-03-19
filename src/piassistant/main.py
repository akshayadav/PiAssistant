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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        run_cli()
    else:
        run_server()
