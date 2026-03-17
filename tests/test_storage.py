import os
import pytest
import pytest_asyncio
from piassistant.config import Settings
from piassistant.services.storage import StorageService


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), anthropic_api_key="test")


@pytest_asyncio.fixture
async def storage(tmp_settings):
    svc = StorageService(tmp_settings)
    await svc.initialize()
    return svc


class TestStorageService:
    @pytest.mark.asyncio
    async def test_initialize_creates_db(self, tmp_settings):
        svc = StorageService(tmp_settings)
        await svc.initialize()
        assert os.path.exists(tmp_settings.db_path)

    @pytest.mark.asyncio
    async def test_health_check(self, storage):
        health = await storage.health_check()
        assert health["healthy"] is True
        assert "0 lists" in health["details"]

    @pytest.mark.asyncio
    async def test_connect_returns_connection(self, storage):
        db = await storage.connect()
        try:
            cursor = await db.execute("SELECT 1")
            row = await cursor.fetchone()
            assert row[0] == 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_schema_tables_exist(self, storage):
        db = await storage.connect()
        try:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [r[0] for r in await cursor.fetchall()]
            assert "lists" in tables
            assert "list_items" in tables
            assert "reminders" in tables
            assert "notes" in tables
        finally:
            await db.close()
