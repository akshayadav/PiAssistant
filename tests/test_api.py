import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from piassistant.api.app import create_app
from piassistant.brain.agent import Agent
from piassistant.config import Settings
from piassistant.services.base import ServiceRegistry
from piassistant.services.cache import CacheService


@pytest.fixture
def settings():
    return Settings(
        anthropic_api_key="test",
        newsapi_key="test",
    )


@pytest.fixture
def app(settings):
    cache = CacheService()
    registry = ServiceRegistry()
    registry.register(cache)

    agent = MagicMock(spec=Agent)
    agent.process = AsyncMock(return_value="Test response")
    agent.reset = MagicMock()

    return create_app(registry, agent, settings)


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_status(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "services" in data


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_returns_response(self, client):
        r = await client.post("/api/chat", json={"message": "hello"})
        assert r.status_code == 200
        assert r.json()["response"] == "Test response"

    @pytest.mark.asyncio
    async def test_chat_requires_message(self, client):
        r = await client.post("/api/chat", json={})
        assert r.status_code == 422


class TestResetEndpoint:
    @pytest.mark.asyncio
    async def test_reset_clears_conversation(self, client):
        r = await client.post("/api/reset")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestPicoEndpoints:
    @pytest.mark.asyncio
    async def test_pico_time(self, client):
        r = await client.get("/api/pico/time")
        assert r.status_code == 200
        data = r.json()
        assert "utc" in data
        assert "epoch" in data


class TestPicoWeather:
    """Tests for /api/pico/weather with units support."""

    @pytest.fixture
    def weather_app(self, settings):
        cache = CacheService()
        registry = ServiceRegistry()
        registry.register(cache)

        weather_mock = AsyncMock()
        weather_mock.name = "weather"
        weather_mock.health_check = AsyncMock(return_value={"healthy": True})
        weather_mock.get_current = AsyncMock(return_value={
            "temp_f": 72.0,
            "feels_like_f": 70.0,
            "description": "Clear sky",
            "icon": "clear",
            "humidity": 45,
            "wind_mph": 8.5,
            "weather_code": 0,
            "location": "Test City",
            "lat": 40.0,
            "lon": -74.0,
        })
        registry.register(weather_mock)

        agent = MagicMock(spec=Agent)
        agent.process = AsyncMock(return_value="Test response")
        agent.reset = MagicMock()
        return create_app(registry, agent, settings)

    @pytest_asyncio.fixture
    async def weather_client(self, weather_app):
        transport = ASGITransport(app=weather_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_imperial_default(self, weather_client):
        r = await weather_client.get("/api/pico/weather")
        assert r.status_code == 200
        data = r.json()
        assert data["temp"] == 72.0
        assert data["wind"] == 8.5
        assert data["desc"] == "Clear sky"
        assert data["icon"] == "clear"
        assert data["hum"] == 45
        assert data["wc"] == 0
        assert data["loc"] == "Test City"

    @pytest.mark.asyncio
    async def test_metric_units(self, weather_client):
        r = await weather_client.get("/api/pico/weather?units=metric")
        assert r.status_code == 200
        data = r.json()
        # 72F -> 22.2C
        assert data["temp"] == 22.2
        # 8.5 mph -> 13.7 km/h
        assert data["wind"] == 13.7
        assert data["code"] == 0
        assert data["description"] == "Clear sky"
        assert data["icon"] == "clear"
        assert "time" in data
