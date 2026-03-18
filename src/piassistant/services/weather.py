from __future__ import annotations

import httpx

from ..config import Settings
from .base import BaseService
from .cache import CacheService


# WMO Weather interpretation codes → description
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy hail storm",
}

# WMO codes → icon keys (matching PicoWeather's expected values)
WMO_ICONS = {
    0: "clear", 1: "clear", 2: "cloudy", 3: "overcast",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    56: "drizzle", 57: "drizzle",
    61: "rain", 63: "rain", 65: "rain",
    66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "rain",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}


class WeatherService(BaseService):
    """Open-Meteo weather data with cache-first fetching. No API key required."""

    name = "weather"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

    def __init__(self, settings: Settings, cache: CacheService):
        self.cache = cache
        self.ttl = settings.weather_cache_ttl
        self.default_lat = settings.default_lat
        self.default_lon = settings.default_lon
        self.default_location = settings.default_location
        self._client = httpx.AsyncClient(timeout=10)

    async def geocode(self, location: str) -> tuple[float, float, str]:
        """Resolve a city name to (lat, lon, resolved_name) via Open-Meteo geocoding.

        Handles "City, State/Country" format by searching for the city name
        and matching against the region hint in the results.
        """
        cache_key = f"geo:{location.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # Split "Santa Clara, CA" into city="Santa Clara", hint="CA"
        parts = [p.strip() for p in location.split(",")]
        city_name = parts[0]
        hint = " ".join(parts[1:]).lower() if len(parts) > 1 else ""

        resp = await self._client.get(
            self.GEO_URL,
            params={"name": city_name, "count": 10, "language": "en", "format": "json"},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return self.default_lat, self.default_lon, self.default_location

        # If we have a hint, try to match against admin1, country, or country_code
        r = results[0]
        if hint:
            for candidate in results:
                fields = [
                    candidate.get("admin1", "").lower(),
                    candidate.get("country", "").lower(),
                    candidate.get("country_code", "").lower(),
                ]
                if any(hint in f or f.startswith(hint) for f in fields):
                    r = candidate
                    break

        lat, lon = r["latitude"], r["longitude"]
        name = r.get("name", location)
        admin = r.get("admin1", "")
        resolved = f"{name}, {admin}" if admin else name

        await self.cache.set(cache_key, (lat, lon, resolved), ttl=86400)
        return lat, lon, resolved

    async def get_current(self, lat: float | None = None, lon: float | None = None, location: str | None = None) -> dict:
        """Get current weather. Resolves location name if lat/lon not provided."""
        resolved_name = location or self.default_location
        if location and (lat is None or lon is None):
            lat, lon, resolved_name = await self.geocode(location)
        lat = lat or self.default_lat
        lon = lon or self.default_lon

        cache_key = f"weather:{lat:.2f}:{lon:.2f}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        resp = await self._client.get(
            self.WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
            },
        )
        resp.raise_for_status()
        resp_json = resp.json()
        current = resp_json.get("current", {})

        wmo_code = current.get("weather_code", 0)
        data = {
            "temp_f": current.get("temperature_2m"),
            "feels_like_f": current.get("apparent_temperature"),
            "description": WMO_CODES.get(wmo_code, "Unknown"),
            "icon": WMO_ICONS.get(wmo_code, "clear"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_mph": current.get("wind_speed_10m"),
            "weather_code": wmo_code,
            "location": resolved_name,
            "lat": lat,
            "lon": lon,
            "timezone": resp_json.get("timezone", "UTC"),
        }
        await self.cache.set(cache_key, data, self.ttl)
        return data

    async def get_forecast(self, lat: float | None = None, lon: float | None = None, location: str | None = None, days: int = 3) -> list[dict]:
        """Get daily weather forecast."""
        resolved_name = location or self.default_location
        if location and (lat is None or lon is None):
            lat, lon, resolved_name = await self.geocode(location)
        lat = lat or self.default_lat
        lon = lon or self.default_lon

        cache_key = f"forecast:{lat:.2f}:{lon:.2f}:{days}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        resp = await self._client.get(
            self.WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,wind_speed_10m_max,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "forecast_days": days,
            },
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})

        forecasts = []
        dates = daily.get("time", [])
        for i, date in enumerate(dates):
            forecasts.append({
                "date": date,
                "temp_max_f": daily["temperature_2m_max"][i],
                "temp_min_f": daily["temperature_2m_min"][i],
                "description": WMO_CODES.get(daily["weather_code"][i], "Unknown"),
                "wind_max_mph": daily["wind_speed_10m_max"][i],
                "precip_chance": daily["precipitation_probability_max"][i],
                "location": resolved_name,
            })
        await self.cache.set(cache_key, forecasts, self.ttl)
        return forecasts

    async def health_check(self) -> dict:
        return {"healthy": True, "details": "Open-Meteo (no key required)"}
