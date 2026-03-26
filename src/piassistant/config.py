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

    # Quote
    quote_cache_ttl: int = 86400  # 24 hours

    # Calendar
    google_calendar_credentials_json: str = ""
    google_calendar_token_path: str = "data/google_token.json"
    icloud_caldav_email: str = ""
    icloud_caldav_password: str = ""
    calendar_cache_ttl: int = 900  # 15 minutes

    # Task management
    stale_task_days: int = 3           # days before unscheduled task is stale
    stale_check_interval: int = 300    # seconds between stale checks (5 min)

    # Assistant
    assistant_name: str = "Bunty"

    # Terminal (SSH bridge to Mac Mini — optional)
    terminal_ssh_host: str = ""
    terminal_ssh_user: str = ""
    terminal_ssh_key: str = ""
    terminal_ssh_port: int = 22
    terminal_password: str = ""  # Required to use terminal; empty = terminal disabled

    # TTS (Text-to-Speech)
    tts_kokoro_url: str = ""          # Kokoro-FastAPI on Mac Mini, e.g. "http://macmini.local:8880"
    tts_kokoro_voice: str = "af_nova" # Kokoro voice name
    tts_piper_enabled: bool = True    # Enable Piper TTS fallback on Pi
    tts_piper_model: str = ""         # Path to Piper .onnx voice model (empty = disabled)
    tts_speed: float = 1.0            # Speech speed multiplier

    # API key for protecting write endpoints (POST/PUT/DELETE/PATCH)
    # Leave empty to allow all requests (local-only mode)
    api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
