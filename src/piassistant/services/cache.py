from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .base import BaseService


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class CacheService(BaseService):
    """In-memory TTL cache. No external dependencies."""

    name = "cache"

    def __init__(self):
        self._store: dict[str, CacheEntry] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = CacheEntry(value=value, expires_at=time.time() + ttl)

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    async def health_check(self) -> dict:
        # Prune expired entries
        now = time.time()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]
        return {"healthy": True, "details": f"{len(self._store)} cached entries"}
