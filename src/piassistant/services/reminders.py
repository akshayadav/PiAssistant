from __future__ import annotations

from .base import BaseService
from .storage import StorageService


class ReminderService(BaseService):
    """Notes backed by SQLite. Reminders have been unified into TaskService."""

    name = "reminders"

    def __init__(self, storage: StorageService):
        self.storage = storage

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
        notes = await self.list_notes()
        return {
            "healthy": True,
            "details": f"{len(notes)} notes",
        }
