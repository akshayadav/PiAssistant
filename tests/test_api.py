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
