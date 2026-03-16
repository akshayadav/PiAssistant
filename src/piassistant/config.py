from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Weather (Open-Meteo — no API key needed)
    default_location: str = "Idaho Falls, ID"
    default_lat: float = 43.49
    default_lon: float = -112.03

    # News (NewsAPI)
    newsapi_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Cache TTLs (seconds)
    weather_cache_ttl: int = 900   # 15 minutes
    news_cache_ttl: int = 1800     # 30 minutes

    # Assistant
    assistant_name: str = "PiAssistant"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
