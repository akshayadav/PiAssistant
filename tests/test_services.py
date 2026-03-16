import asyncio
import pytest
from piassistant.services.base import BaseService, ServiceRegistry
from piassistant.services.cache import CacheService


class DummyService(BaseService):
    name = "dummy"

    async def health_check(self):
        return {"healthy": True, "details": "test"}


@pytest.fixture
def registry():
    return ServiceRegistry()


@pytest.fixture
def cache():
    return CacheService()


class TestServiceRegistry:
    def test_register_and_get(self, registry):
        svc = DummyService()
        registry.register(svc)
        assert registry.get("dummy") is svc

    def test_get_missing_raises(self, registry):
        with pytest.raises(KeyError, match="not_here"):
            registry.get("not_here")

    @pytest.mark.asyncio
    async def test_initialize_all(self, registry):
        registry.register(DummyService())
        await registry.initialize_all()  # should not raise

    @pytest.mark.asyncio
    async def test_health_check_all(self, registry):
        registry.register(DummyService())
        results = await registry.health_check_all()
        assert results["dummy"]["healthy"] is True


class TestCacheService:
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("key1", {"data": 42}, ttl=60)
        result = await cache.get("key1")
        assert result == {"data": 42}

    @pytest.mark.asyncio
    async def test_get_missing(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entry(self, cache):
        await cache.set("key2", "value", ttl=0)  # expires immediately
        result = await cache.get("key2")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate(self, cache):
        await cache.set("key3", "value", ttl=60)
        await cache.invalidate("key3")
        result = await cache.get("key3")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("a", 1, ttl=60)
        await cache.set("b", 2, ttl=60)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    @pytest.mark.asyncio
    async def test_health_check(self, cache):
        await cache.set("x", 1, ttl=60)
        health = await cache.health_check()
        assert health["healthy"] is True
        assert "1 cached" in health["details"]
