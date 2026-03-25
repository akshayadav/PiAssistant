from __future__ import annotations

from pathlib import Path

import aiosqlite

from ..config import Settings
from .base import BaseService

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    quantity TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT,
    for_person TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    for_person TEXT DEFAULT '',
    pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    priority TEXT DEFAULT '',
    due_at TEXT DEFAULT '',
    is_reminder INTEGER DEFAULT 0,
    for_person TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weather_cities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    country TEXT DEFAULT '',
    category TEXT DEFAULT 'general',
    query TEXT DEFAULT '',
    count INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


class StorageService(BaseService):
    """SQLite persistence layer via aiosqlite."""

    name = "storage"

    def __init__(self, settings: Settings):
        self.db_path = settings.db_path

    async def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.executescript(SCHEMA)
            # Migrations for columns added after initial schema
            try:
                await db.execute(
                    "ALTER TABLE news_feeds ADD COLUMN provider TEXT DEFAULT 'newsapi'"
                )
            except Exception:
                pass  # Column already exists
            await db.commit()

    async def health_check(self) -> dict:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM lists) AS lists, "
                    "(SELECT COUNT(*) FROM list_items) AS items, "
                    "(SELECT COUNT(*) FROM reminders) AS reminders, "
                    "(SELECT COUNT(*) FROM notes) AS notes"
                )
                row = await cursor.fetchone()
                return {
                    "healthy": True,
                    "details": f"{row[0]} lists, {row[1]} items, {row[2]} reminders, {row[3]} notes",
                }
        except Exception as e:
            return {"healthy": False, "details": str(e)}

    async def connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        return db
