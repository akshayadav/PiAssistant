from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..config import Settings
from .base import BaseService
from .storage import StorageService

logger = logging.getLogger(__name__)


class TaskService(BaseService):
    """Unified task and reminder management backed by SQLite with stale-task nudging."""

    name = "todo"

    def __init__(self, storage: StorageService, settings: Settings):
        self.storage = storage
        self.settings = settings
        self._nudges: list[dict] = []
        self._stale_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        await self._migrate_legacy_data()
        self._stale_task = asyncio.create_task(self._stale_checker())

    async def _migrate_legacy_data(self) -> None:
        """One-time migration: copy old list_items (todos) and reminders into tasks table."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute("SELECT COUNT(*) FROM tasks")
            row = await cursor.fetchone()
            if row[0] > 0:
                return  # Already migrated

            # Migrate todos from list_items
            cursor = await db.execute(
                "SELECT li.text, li.quantity, li.done, li.created_at "
                "FROM list_items li JOIN lists l ON li.list_id = l.id "
                "WHERE l.type = 'todo'"
            )
            for r in await cursor.fetchall():
                await db.execute(
                    "INSERT INTO tasks (text, priority, done, created_at) VALUES (?, ?, ?, ?)",
                    (r[0], r[1] or "", r[2], r[3]),
                )

            # Migrate reminders
            cursor = await db.execute(
                "SELECT text, due_at, for_person, done, created_at FROM reminders"
            )
            for r in await cursor.fetchall():
                await db.execute(
                    "INSERT INTO tasks (text, due_at, for_person, is_reminder, done, created_at) "
                    "VALUES (?, ?, ?, 1, ?, ?)",
                    (r[0], r[1] or "", r[2] or "", r[3], r[4]),
                )

            await db.commit()
            logger.info("Migrated legacy todos and reminders into tasks table")
        except Exception as e:
            logger.warning("Legacy data migration skipped: %s", e)
        finally:
            await db.close()

    async def add_task(
        self,
        text: str,
        priority: str = "",
        due_at: str = "",
        is_reminder: bool = False,
        for_person: str = "",
    ) -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT INTO tasks (text, priority, due_at, is_reminder, for_person) "
                "VALUES (?, ?, ?, ?, ?)",
                (text, priority, due_at, int(is_reminder), for_person),
            )
            await db.commit()
            return {
                "id": cursor.lastrowid,
                "text": text,
                "priority": priority,
                "due_at": due_at,
                "is_reminder": is_reminder,
                "for_person": for_person,
            }
        finally:
            await db.close()

    async def get_tasks(self, include_done: bool = False) -> list[dict]:
        db = await self.storage.connect()
        try:
            where = "WHERE done = 0" if not include_done else ""
            cursor = await db.execute(
                f"SELECT id, text, priority, due_at, is_reminder, for_person, "
                f"done, completed_at, created_at, updated_at "
                f"FROM tasks {where} "
                f"ORDER BY done, "
                f"CASE WHEN due_at != '' AND due_at < datetime('now') THEN 0 ELSE 1 END, "
                f"CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, "
                f"CASE WHEN due_at != '' THEN due_at ELSE '9999-12-31' END, "
                f"created_at"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "text": r[1],
                    "priority": r[2],
                    "due_at": r[3],
                    "is_reminder": bool(r[4]),
                    "for_person": r[5],
                    "done": bool(r[6]),
                    "completed_at": r[7],
                    "created_at": r[8],
                    "updated_at": r[9],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def get_task(self, task_id: int) -> dict | None:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id, text, priority, due_at, is_reminder, for_person, "
                "done, completed_at, created_at, updated_at "
                "FROM tasks WHERE id = ?",
                (task_id,),
            )
            r = await cursor.fetchone()
            if not r:
                return None
            return {
                "id": r[0],
                "text": r[1],
                "priority": r[2],
                "due_at": r[3],
                "is_reminder": bool(r[4]),
                "for_person": r[5],
                "done": bool(r[6]),
                "completed_at": r[7],
                "created_at": r[8],
                "updated_at": r[9],
            }
        finally:
            await db.close()

    async def complete_task(self, task_id: int) -> bool:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "UPDATE tasks SET done = 1, completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, task_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def delete_task(self, task_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def update_task(
        self, task_id: int, text: str | None = None, priority: str | None = None, due_at: str | None = None
    ) -> dict | None:
        sets = []
        params: list = []
        if text is not None:
            sets.append("text = ?")
            params.append(text)
        if priority is not None:
            sets.append("priority = ?")
            params.append(priority)
        if due_at is not None:
            sets.append("due_at = ?")
            params.append(due_at)
        if not sets:
            return await self.get_task(task_id)

        sets.append("updated_at = datetime('now')")
        params.append(task_id)

        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params
            )
            await db.commit()
            if cursor.rowcount == 0:
                return None
            return await self.get_task(task_id)
        finally:
            await db.close()

    def get_nudges(self) -> list[dict]:
        return list(self._nudges)

    async def _stale_checker(self) -> None:
        """Background loop: refresh nudges for overdue/stale tasks."""
        while True:
            try:
                await self._refresh_nudges()
            except Exception as e:
                logger.warning("Stale task check failed: %s", e)
            await asyncio.sleep(self.settings.stale_check_interval)

    async def _refresh_nudges(self) -> None:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.settings.stale_task_days)).strftime("%Y-%m-%dT%H:%M:%S")
        now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

        db = await self.storage.connect()
        try:
            nudges = []

            # Overdue tasks (have a due_at in the past)
            cursor = await db.execute(
                "SELECT id, text FROM tasks WHERE done = 0 AND due_at != '' AND due_at < ?",
                (now_str,),
            )
            for r in await cursor.fetchall():
                nudges.append({"task_id": r[0], "text": r[1], "reason": "overdue"})

            # Stale tasks (no due_at AND no priority, created more than N days ago)
            cursor = await db.execute(
                "SELECT id, text FROM tasks "
                "WHERE done = 0 AND due_at = '' AND priority = '' AND created_at < ?",
                (cutoff,),
            )
            for r in await cursor.fetchall():
                nudges.append({"task_id": r[0], "text": r[1], "reason": "needs attention"})

            self._nudges = nudges
        finally:
            await db.close()

    async def health_check(self) -> dict:
        tasks = await self.get_tasks()
        nudge_count = len(self._nudges)
        return {
            "healthy": True,
            "details": f"{len(tasks)} active tasks, {nudge_count} nudges",
        }
