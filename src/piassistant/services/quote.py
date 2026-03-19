from __future__ import annotations

import logging
from datetime import date

import httpx

from ..config import Settings
from .base import BaseService
from .cache import CacheService
from .storage import StorageService

logger = logging.getLogger(__name__)

FALLBACK_QUOTES = [
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("Any sufficiently advanced technology is indistinguishable from magic.", "Arthur C. Clarke"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("In the middle of difficulty lies opportunity.", "Albert Einstein"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("The computer was born to solve problems that did not exist before.", "Bill Gates"),
]


class QuoteService(BaseService):
    """Daily inspirational quote via zenquotes.io with SQLite persistence."""

    name = "quote"

    def __init__(self, storage: StorageService, cache: CacheService, settings: Settings):
        self.storage = storage
        self.cache = cache
        self.cache_ttl = settings.quote_cache_ttl

    async def initialize(self) -> None:
        db = await self.storage.connect()
        try:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS daily_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote TEXT NOT NULL,
                    author TEXT NOT NULL,
                    date TEXT NOT NULL UNIQUE,
                    created_at TEXT DEFAULT (datetime('now'))
                )"""
            )
            await db.commit()
        finally:
            await db.close()

    async def get_daily_quote(self) -> dict:
        """Get today's quote. Check cache → DB → API → fallback."""
        today = date.today().isoformat()
        cache_key = "quote:daily"

        # Check cache
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        # Check DB for today's quote
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT quote, author FROM daily_quotes WHERE date = ?", (today,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()

        if row:
            result = {"quote": row[0], "author": row[1], "date": today}
            await self.cache.set(cache_key, result, self.cache_ttl)
            return result

        # Fetch from API
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://zenquotes.io/api/today")
                resp.raise_for_status()
                data = resp.json()
                if data and isinstance(data, list) and data[0].get("q"):
                    quote_text = data[0]["q"]
                    author = data[0].get("a", "Unknown")
                    result = {"quote": quote_text, "author": author, "date": today}
                    # Store in DB
                    db = await self.storage.connect()
                    try:
                        await db.execute(
                            "INSERT OR IGNORE INTO daily_quotes (quote, author, date) VALUES (?, ?, ?)",
                            (quote_text, author, today),
                        )
                        await db.commit()
                    finally:
                        await db.close()
                    await self.cache.set(cache_key, result, self.cache_ttl)
                    return result
        except Exception as e:
            logger.warning("Failed to fetch daily quote: %s", e)

        # Fallback
        idx = date.today().toordinal() % len(FALLBACK_QUOTES)
        q, a = FALLBACK_QUOTES[idx]
        result = {"quote": q, "author": a, "date": today}
        await self.cache.set(cache_key, result, self.cache_ttl)
        return result

    async def health_check(self) -> dict:
        try:
            db = await self.storage.connect()
            try:
                cursor = await db.execute("SELECT COUNT(*) FROM daily_quotes")
                row = await cursor.fetchone()
                count = row[0]
            finally:
                await db.close()
            return {"healthy": True, "details": f"{count} quotes stored"}
        except Exception as e:
            return {"healthy": False, "details": str(e)}
