from __future__ import annotations

from .base import BaseService
from .storage import StorageService


class ReminderService(BaseService):
    """Reminders and notes backed by SQLite."""

    name = "reminders"

    def __init__(self, storage: StorageService):
        self.storage = storage

    async def add_reminder(self, text: str, due_at: str = "", for_person: str = "") -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT INTO reminders (text, due_at, for_person) VALUES (?, ?, ?)",
                (text, due_at, for_person),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "text": text, "due_at": due_at, "for_person": for_person}
        finally:
            await db.close()

    async def list_reminders(self, include_done: bool = False) -> list[dict]:
        db = await self.storage.connect()
        try:
            where = "" if include_done else "WHERE done = 0"
            cursor = await db.execute(
                f"SELECT id, text, due_at, for_person, done, created_at "
                f"FROM reminders {where} ORDER BY due_at IS NULL, due_at, created_at"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "text": r[1], "due_at": r[2],
                    "for_person": r[3], "done": bool(r[4]), "created_at": r[5],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def complete_reminder(self, reminder_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def delete_reminder(self, reminder_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def add_note(self, text: str, for_person: str = "", pinned: bool = False) -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT INTO notes (text, for_person, pinned) VALUES (?, ?, ?)",
                (text, for_person, int(pinned)),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "text": text, "for_person": for_person, "pinned": pinned}
        finally:
            await db.close()

    async def list_notes(self) -> list[dict]:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id, text, for_person, pinned, created_at "
                "FROM notes ORDER BY pinned DESC, created_at DESC"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "text": r[1], "for_person": r[2],
                    "pinned": bool(r[3]), "created_at": r[4],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def delete_note(self, note_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def health_check(self) -> dict:
        reminders = await self.list_reminders()
        notes = await self.list_notes()
        return {
            "healthy": True,
            "details": f"{len(reminders)} active reminders, {len(notes)} notes",
        }
