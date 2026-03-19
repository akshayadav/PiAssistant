from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Weather (Open-Meteo — no API key needed)
    default_location: str = "Idaho Falls, ID"
    default_lat: float = 43.49
    default_lon: float = -112.03

    # News
    newsapi_key: str = ""          # NewsAPI.org
    newsdata_api_key: str = ""     # Newsdata.io

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Cache TTLs (seconds)
    weather_cache_ttl: int = 900   # 15 minutes
    news_cache_ttl: int = 1800     # 30 minutes
    news_dashboard_ttl: int = 21600  # 6 hours for dashboard feeds

    # Database
    db_path: str = "data/piassistant.db"

    # Amazon Orders
    amazon_email: str = ""
    amazon_password: str = ""
    amazon_otp_secret: str = ""
    amazon_refresh_interval: int = 14400   # 4 hours
    amazon_min_refresh_gap: int = 900      # 15 min between manual refreshes

    # Assistant
    assistant_name: str = "PiAssistant"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
