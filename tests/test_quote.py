import pytest
import pytest_asyncio
from datetime import date

from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.cache import CacheService
from piassistant.services.quote import QuoteService


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), anthropic_api_key="test")


@pytest_asyncio.fixture
async def storage(tmp_settings):
    svc = StorageService(tmp_settings)
    await svc.initialize()
    return svc


@pytest_asyncio.fixture
async def cache():
    return CacheService()


@pytest_asyncio.fixture
async def quote_service(storage, cache, tmp_settings):
    svc = QuoteService(storage, cache, tmp_settings)
    await svc.initialize()
    return svc


class TestQuoteService:
    @pytest.mark.asyncio
    async def test_store_and_retrieve_quote(self, quote_service, storage):
        """Store a quote in DB, verify it's returned."""
        today = date.today().isoformat()
        db = await storage.connect()
        try:
            await db.execute(
                "INSERT INTO daily_quotes (quote, author, date) VALUES (?, ?, ?)",
                ("Test quote", "Test Author", today),
            )
            await db.commit()
        finally:
            await db.close()

        result = await quote_service.get_daily_quote()
        assert result["quote"] == "Test quote"
        assert result["author"] == "Test Author"
        assert result["date"] == today

    @pytest.mark.asyncio
    async def test_fallback_when_no_data(self, quote_service):
        """With no DB entry and no API, should return a fallback quote."""
        result = await quote_service.get_daily_quote()
        assert "quote" in result
        assert "author" in result
        assert "date" in result
        assert len(result["quote"]) > 0

    @pytest.mark.asyncio
    async def test_health_check(self, quote_service):
        health = await quote_service.health_check()
        assert health["healthy"] is True
        assert "0 quotes" in health["details"]

    @pytest.mark.asyncio
    async def test_cache_returns_cached_value(self, quote_service, cache):
        """Second call should come from cache."""
        result1 = await quote_service.get_daily_quote()
        # Verify it's cached
        cached = await cache.get("quote:daily")
        assert cached is not None
        assert cached["quote"] == result1["quote"]

        # Second call returns same
        result2 = await quote_service.get_daily_quote()
        assert result2["quote"] == result1["quote"]
