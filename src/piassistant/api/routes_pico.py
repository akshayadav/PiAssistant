import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/weather")
async def pico_weather(
    request: Request,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    location: Optional[str] = None,
    units: str = "imperial",
):
    """Compact weather for Pico W devices. Use units=metric for Celsius/km/h."""
    settings = request.app.state.settings
    weather = request.app.state.registry.get("weather")
    data = await weather.get_current(
        lat=lat,
        lon=lon,
        location=location or settings.default_location,
    )

    if units == "metric":
        temp_c = round((data["temp_f"] - 32) * 5 / 9, 1)
        wind_kmh = round(data["wind_mph"] * 1.60934, 1)
        return {
            "temp": temp_c,
            "wind": wind_kmh,
            "code": data["weather_code"],
            "description": data["description"],
            "icon": data["icon"],
            "time": int(time.time()),
        }

    return {
        "temp": data["temp_f"],
        "feel": data["feels_like_f"],
        "desc": data["description"],
        "icon": data["icon"],
        "hum": data["humidity"],
        "wind": data["wind_mph"],
        "wc": data["weather_code"],
        "loc": data["location"],
    }


@router.get("/news")
async def pico_news(request: Request, category: str = "general", count: int = 3):
    """Compact news headlines for Pico W devices."""
    news = request.app.state.registry.get("news")
    articles = await news.get_headlines(category=category, count=count)
    return [{"t": a["title"], "s": a["source"]} for a in articles]


@router.get("/time")
async def pico_time():
    """Current time for Pico W clock sync."""
    now = datetime.now(timezone.utc)
    return {"utc": now.isoformat(), "epoch": int(now.timestamp())}
