import asyncio
import sys

import uvicorn

from .config import Settings
from .services.base import ServiceRegistry
from .services.cache import CacheService
from .services.llm import LLMService
from .services.weather import WeatherService
from .services.news import NewsService
from .brain.agent import Agent
from .api.app import create_app


def run_server():
    settings = Settings()

    # Build services
    cache = CacheService()
    llm = LLMService(settings)
    weather = WeatherService(settings, cache)
    news = NewsService(settings, cache)

    # Register
    registry = ServiceRegistry()
    registry.register(cache)
    registry.register(llm)
    registry.register(weather)
    registry.register(news)

    # Brain
    agent = Agent(llm, registry, settings)

    # App
    app = create_app(registry, agent, settings)

    uvicorn.run(app, host=settings.host, port=settings.port)


def run_cli():
    from .cli.repl import repl
    asyncio.run(repl())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        run_cli()
    else:
        run_server()
