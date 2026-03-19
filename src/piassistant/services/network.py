from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime, timezone

from .base import BaseService
from .storage import StorageService

logger = logging.getLogger(__name__)

DEFAULT_NETWORK_DEVICES = [
    ("Pi 5 (self)", "localhost", "127.0.0.1", "pi"),
    ("Mac Mini", "Akshays-Mac-mini.local", "10.0.0.131", "mac"),
]


class NetworkService(BaseService):
    """Network device monitoring via ping."""

    name = "network"

    def __init__(self, storage: StorageService):
        self.storage = storage
        self._ping_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        db = await self.storage.connect()
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

            # Seed defaults if table is empty
            cursor = await db.execute("SELECT COUNT(*) FROM network_devices")
            row = await cursor.fetchone()
            if row[0] == 0:
                for name, hostname, ip, dtype in DEFAULT_NETWORK_DEVICES:
                    await db.execute(
                        "INSERT INTO network_devices (name, hostname, ip, device_type) VALUES (?, ?, ?, ?)",
                        (name, hostname, ip, dtype),
                    )
                await db.commit()
        finally:
            await db.close()

        # Start background pinger
        self._ping_task = asyncio.create_task(self._background_pinger())

    async def list_devices(self) -> list[dict]:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id, name, hostname, ip, device_type, last_seen, is_online "
                "FROM network_devices ORDER BY id"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "hostname": r[2],
                    "ip": r[3],
                    "device_type": r[4],
                    "last_seen": r[5],
                    "is_online": bool(r[6]),
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def add_device(self, name: str, hostname: str, ip: str = "", device_type: str = "other") -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT INTO network_devices (name, hostname, ip, device_type) VALUES (?, ?, ?, ?)",
                (name, hostname, ip, device_type),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "name": name, "hostname": hostname}
        finally:
            await db.close()

    async def remove_device(self, device_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM network_devices WHERE id = ?", (device_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def ping_device(self, hostname: str) -> bool:
        """Ping a hostname, return True if reachable."""
        try:
            # Platform-aware ping flags
            if platform.system() == "Darwin":
                args = ["ping", "-c", "1", "-t", "2", hostname]
            else:
                args = ["ping", "-c", "1", "-W", "2", hostname]

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            return proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            return False

    async def ping_all(self) -> list[dict]:
        """Ping all devices and update their status."""
        devices = await self.list_devices()
        if not devices:
            return []

        async def ping_one(device):
            online = await self.ping_device(device["hostname"])
            return device["id"], online

        results = await asyncio.gather(*[ping_one(d) for d in devices])

        now = datetime.now(timezone.utc).isoformat()
        db = await self.storage.connect()
        try:
            for device_id, online in results:
                if online:
                    await db.execute(
                        "UPDATE network_devices SET is_online = 1, last_seen = ? WHERE id = ?",
                        (now, device_id),
                    )
                else:
                    await db.execute(
                        "UPDATE network_devices SET is_online = 0 WHERE id = ?",
                        (device_id,),
                    )
            await db.commit()
        finally:
            await db.close()

        return await self.list_devices()

    async def _background_pinger(self) -> None:
        """Ping all devices every 60 seconds."""
        while True:
            try:
                await self.ping_all()
            except Exception as e:
                logger.warning("Background ping failed: %s", e)
            await asyncio.sleep(60)

    async def health_check(self) -> dict:
        try:
            devices = await self.list_devices()
            online = sum(1 for d in devices if d["is_online"])
            return {
                "healthy": True,
                "details": f"{online}/{len(devices)} devices online",
            }
        except Exception as e:
            return {"healthy": False, "details": str(e)}
