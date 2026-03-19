import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.network import NetworkService


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), anthropic_api_key="test")


@pytest_asyncio.fixture
async def storage(tmp_settings):
    svc = StorageService(tmp_settings)
    await svc.initialize()
    return svc


@pytest_asyncio.fixture
async def network(storage):
    svc = NetworkService(storage)
    # Initialize without starting the background pinger
    db = await storage.connect()
    try:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS network_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT DEFAULT '',
                device_type TEXT DEFAULT 'other',
                last_seen TEXT,
                is_online INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )"""
        )
        await db.commit()
    finally:
        await db.close()
    return svc


class TestNetworkService:
    @pytest.mark.asyncio
    async def test_add_and_list_device(self, network):
        result = await network.add_device("Test Device", "test.local", "10.0.0.99", "other")
        assert result["name"] == "Test Device"
        assert result["hostname"] == "test.local"

        devices = await network.list_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Test Device"
        assert devices[0]["is_online"] is False

    @pytest.mark.asyncio
    async def test_remove_device(self, network):
        result = await network.add_device("To Remove", "remove.local")
        device_id = result["id"]

        removed = await network.remove_device(device_id)
        assert removed is True

        devices = await network.list_devices()
        assert len(devices) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, network):
        removed = await network.remove_device(9999)
        assert removed is False

    @pytest.mark.asyncio
    async def test_ping_device_success(self, network):
        """Mock a successful ping."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await network.ping_device("localhost")
            assert result is True

    @pytest.mark.asyncio
    async def test_ping_device_failure(self, network):
        """Mock a failed ping."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.wait = AsyncMock(return_value=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await network.ping_device("nonexistent.local")
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check(self, network):
        health = await network.health_check()
        assert health["healthy"] is True
        assert "devices online" in health["details"]
