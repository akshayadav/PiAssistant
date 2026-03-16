from __future__ import annotations

import httpx

from ..config import Settings
from .base import BaseService
from .cache import CacheService


class WeatherService(BaseService):
    """OpenWeatherMap weather data with cache-first fetching."""

    name = "weather"
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"

    def __init__(self, settings: Settings, cache: CacheService):
        self.api_key = settings.openweathermap_api_key
        self.cache = cache
        self.ttl = settings.weather_cache_ttl
        self.default_lat = settings.default_lat
        self.default_lon = settings.default_lon
        self.default_location = settings.default_location
        self._client = httpx.AsyncClient(timeout=10)

    async def geocode(self, location: str) -> tuple[float, float]:
        """Resolve a city name to lat/lon via OpenWeatherMap geocoding API."""
        cache_key = f"geo:{location.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        resp = await self._client.get(
            self.GEO_URL,
            params={"q": location, "limit": 1, "appid": self.api_key},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return self.default_lat, self.default_lon

        lat, lon = results[0]["lat"], results[0]["lon"]
        await self.cache.set(cache_key, (lat, lon), ttl=86400)  # cache 24h
        return lat, lon

    async def get_current(self, lat: float | None = None, lon: float | None = None, location: str | None = None) -> dict:
        """Get current weather. Resolves location name if lat/lon not provided."""
        if location and (lat is None or lon is None):
            lat, lon = await self.geocode(location)
        lat = lat or self.default_lat
        lon = lon or self.default_lon

        cache_key = f"weather:{lat:.2f}:{lon:.2f}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        resp = await self._client.get(
            f"{self.BASE_URL}/weather",
            params={"lat": lat, "lon": lon, "appid": self.api_key, "units": "imperial"},
        )
        resp.raise_for_status()
        raw = resp.json()

        data = {
            "temp_f": raw["main"]["temp"],
            "feels_like_f": raw["main"]["feels_like"],
            "description": raw["weather"][0]["description"],
            "humidity": raw["main"]["humidity"],
            "wind_mph": raw["wind"]["speed"],
            "icon": raw["weather"][0]["icon"],
            "location": raw.get("name", location or self.default_location),
            "lat": lat,
            "lon": lon,
        }
        await self.cache.set(cache_key, data, self.ttl)
        return data

    async def get_forecast(self, lat: float | None = None, lon: float | None = None, location: str | None = None, days: int = 3) -> list[dict]:
        """Get weather forecast. Returns list of forecast entries."""
        if location and (lat is None or lon is None):
            lat, lon = await self.geocode(location)
        lat = lat or self.default_lat
        lon = lon or self.default_lon

        cache_key = f"forecast:{lat:.2f}:{lon:.2f}:{days}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        resp = await self._client.get(
            f"{self.BASE_URL}/forecast",
            params={"lat": lat, "lon": lon, "appid": self.api_key, "units": "imperial", "cnt": days * 8},
        )
        resp.raise_for_status()
        raw = resp.json()

        forecasts = []
        for entry in raw.get("list", []):
            forecasts.append({
                "dt": entry["dt"],
                "dt_txt": entry["dt_txt"],
                "temp_f": entry["main"]["temp"],
                "description": entry["weather"][0]["description"],
                "humidity": entry["main"]["humidity"],
                "wind_mph": entry["wind"]["speed"],
                "icon": entry["weather"][0]["icon"],
            })
        await self.cache.set(cache_key, forecasts, self.ttl)
        return forecasts

    async def health_check(self) -> dict:
        if not self.api_key:
            return {"healthy": False, "details": "No OpenWeatherMap API key"}
        return {"healthy": True, "details": "OpenWeatherMap configured"}
