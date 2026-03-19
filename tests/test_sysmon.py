import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from piassistant.services.cache import CacheService
from piassistant.services.sysmon import SystemMonitorService


@pytest_asyncio.fixture
async def cache():
    return CacheService()


@pytest_asyncio.fixture
async def sysmon(cache):
    return SystemMonitorService(cache)


class TestSystemMonitorService:
    @pytest.mark.asyncio
    async def test_get_status_shape(self, sysmon):
        """Verify output has all expected keys."""
        status = await sysmon.get_status()
        assert "cpu_percent" in status
        assert "memory_percent" in status
        assert "memory_total_gb" in status
        assert "memory_available_gb" in status
        assert "disk_percent" in status
        assert "disk_total_gb" in status
        assert "disk_free_gb" in status
        assert "uptime_seconds" in status
        assert "platform" in status
        assert "cpu_temp_c" in status  # may be None on Mac

    @pytest.mark.asyncio
    async def test_values_reasonable(self, sysmon):
        """CPU and memory percentages should be 0-100."""
        status = await sysmon.get_status()
        assert 0 <= status["cpu_percent"] <= 100
        assert 0 <= status["memory_percent"] <= 100
        assert 0 <= status["disk_percent"] <= 100
        assert status["uptime_seconds"] > 0

    @pytest.mark.asyncio
    async def test_temp_fallback_returns_none_gracefully(self, sysmon):
        """On Mac or systems without temp sensors, cpu_temp_c should be None (not error)."""
        # Clear cache first
        await sysmon.cache.clear()
        with patch("piassistant.services.sysmon.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0
            mock_mem = MagicMock()
            mock_mem.percent = 50.0
            mock_mem.total = 8 * 1024**3
            mock_mem.available = 4 * 1024**3
            mock_psutil.virtual_memory.return_value = mock_mem
            mock_disk = MagicMock()
            mock_disk.percent = 40.0
            mock_disk.total = 500 * 1024**3
            mock_disk.free = 300 * 1024**3
            mock_psutil.disk_usage.return_value = mock_disk
            mock_psutil.boot_time.return_value = 0
            # No sensors_temperatures attribute
            del mock_psutil.sensors_temperatures
            status = await sysmon.get_status()
            # Should not raise — cpu_temp_c is None
            assert status["cpu_temp_c"] is None

    @pytest.mark.asyncio
    async def test_health_check(self, sysmon):
        health = await sysmon.health_check()
        assert health["healthy"] is True
        assert "CPU" in health["details"]
        assert "RAM" in health["details"]

    @pytest.mark.asyncio
    async def test_caching(self, sysmon, cache):
        """Second call within 10s should return cached result."""
        result1 = await sysmon.get_status()
        cached = await cache.get("sysmon:status")
        assert cached is not None
        assert cached["platform"] == result1["platform"]
