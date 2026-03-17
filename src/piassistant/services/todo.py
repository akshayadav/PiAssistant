from __future__ import annotations

from .base import BaseService
from .storage import StorageService

DEFAULT_TODO_LIST = "Todo"


class TodoService(BaseService):
    """To-do list management backed by SQLite."""

    name = "todo"

    def __init__(self, storage: StorageService):
        self.storage = storage

    async def initialize(self) -> None:
        db = await self.storage.connect()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO lists (name, type) VALUES (?, 'todo')",
                (DEFAULT_TODO_LIST,),
            )
            await db.commit()
        finally:
            await db.close()

    async def add_item(self, text: str, priority: str = "") -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id FROM lists WHERE name = ? AND type = 'todo'",
                (DEFAULT_TODO_LIST,),
            )
            row = await cursor.fetchone()
            list_id = row[0]

            cursor = await db.execute(
                "INSERT INTO list_items (list_id, text, quantity) VALUES (?, ?, ?)",
                (list_id, text, priority),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "text": text, "priority": priority}
        finally:
            await db.close()

    async def get_list(self, include_done: bool = False) -> list[dict]:
        db = await self.storage.connect()
        try:
            where = "AND li.done = 0" if not include_done else ""
            cursor = await db.execute(
                f"SELECT li.id, li.text, li.quantity AS priority, li.done "
                f"FROM list_items li JOIN lists l ON li.list_id = l.id "
                f"WHERE l.type = 'todo' {where} "
                f"ORDER BY li.done, li.created_at"
            )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "text": r[1], "priority": r[2], "done": bool(r[3])}
                for r in rows
            ]
        finally:
            await db.close()

    async def complete_item(self, item_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "UPDATE list_items SET done = 1 WHERE id = ?", (item_id,)
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def delete_item(self, item_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def health_check(self) -> dict:
        items = await self.get_list()
        return {"healthy": True, "details": f"{len(items)} active todos"}
