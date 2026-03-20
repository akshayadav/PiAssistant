import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from piassistant.api.app import create_app
from piassistant.brain.agent import Agent
from piassistant.config import Settings
from piassistant.services.base import ServiceRegistry
from piassistant.services.cache import CacheService


def make_app(api_key: str = ""):
    settings = Settings(anthropic_api_key="test", newsapi_key="test", api_key=api_key)
    cache = CacheService()
    registry = ServiceRegistry()
    registry.register(cache)
    agent = MagicMock(spec=Agent)
    agent.process = AsyncMock(return_value="Test response")
    agent.reset = MagicMock()
    return create_app(registry, agent, settings)


class TestNoApiKeyConfigured:
    """When API_KEY is empty, all requests pass through (backward compatible)."""

    @pytest_asyncio.fixture
    async def client(self):
        app = make_app(api_key="")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_get_passes(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_post_passes_without_key(self, client):
        r = await client.post("/api/chat", json={"message": "hello"})
        assert r.status_code == 200


class TestApiKeyConfigured:
    """When API_KEY is set, write endpoints require Bearer token."""

    @pytest_asyncio.fixture
    async def client(self):
        app = make_app(api_key="secret123")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_get_passes_without_key(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_post_blocked_without_key(self, client):
        r = await client.post("/api/chat", json={"message": "hello"})
        assert r.status_code == 401
        assert "API key" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_post_blocked_with_wrong_key(self, client):
        r = await client.post(
            "/api/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_post_passes_with_correct_key(self, client):
        r = await client.post(
            "/api/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer secret123"},
        )
        assert r.status_code == 200
        assert r.json()["response"] == "Test response"

    @pytest.mark.asyncio
    async def test_dashboard_passes_without_key(self, client):
        r = await client.get("/")
        assert r.status_code == 200
