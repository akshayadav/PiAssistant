from __future__ import annotations

import platform
import time

import psutil

from .base import BaseService
from .cache import CacheService


class SystemMonitorService(BaseService):
    """Live system metrics via psutil."""

    name = "sysmon"

    def __init__(self, cache: CacheService):
        self.cache = cache

    async def get_status(self) -> dict:
        """Get current system status. Cached for 10 seconds."""
        cache_key = "sysmon:status"
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot = psutil.boot_time()
        uptime = int(time.time() - boot)

        # CPU temperature
        cpu_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Linux (Pi): 'cpu_thermal' or first available
                for name in ("cpu_thermal", "coretemp"):
                    if name in temps and temps[name]:
                        cpu_temp = temps[name][0].current
                        break
                if cpu_temp is None:
                    # Use first available sensor
                    first = next(iter(temps.values()), [])
                    if first:
                        cpu_temp = first[0].current
        except (AttributeError, StopIteration):
            pass

        # Pi-specific fallback
        if cpu_temp is None:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    cpu_temp = int(f.read().strip()) / 1000.0
            except (FileNotFoundError, ValueError):
                pass

        result = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": mem.percent,
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "memory_available_gb": round(mem.available / (1024**3), 1),
            "disk_percent": disk.percent,
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
            "cpu_temp_c": round(cpu_temp, 1) if cpu_temp is not None else None,
            "uptime_seconds": uptime,
            "platform": platform.system(),
        }

        await self.cache.set(cache_key, result, 10)
        return result

    async def health_check(self) -> dict:
        mem = psutil.virtual_memory()
        return {
            "healthy": True,
            "details": f"CPU {psutil.cpu_percent()}%, RAM {mem.percent}%",
        }
