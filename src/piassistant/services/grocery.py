from __future__ import annotations

from .base import BaseService
from .storage import StorageService

DEFAULT_STORES = [
    "Whole Foods",
    "Sprouts",
    "Indian Grocery",
    "Costco",
    "Target",
    "Other",
]


class GroceryService(BaseService):
    """Grocery list management backed by SQLite."""

    name = "grocery"

    def __init__(self, storage: StorageService):
        self.storage = storage

    async def initialize(self) -> None:
        db = await self.storage.connect()
        try:
            for store in DEFAULT_STORES:
                await db.execute(
                    "INSERT OR IGNORE INTO lists (name, type) VALUES (?, 'grocery')",
                    (store,),
                )
            await db.commit()
        finally:
            await db.close()

    async def add_item(self, store: str, item: str, quantity: str = "") -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id FROM lists WHERE name = ? AND type = 'grocery'", (store,)
            )
            row = await cursor.fetchone()
            if not row:
                # Create the store list on-the-fly
                cursor = await db.execute(
                    "INSERT INTO lists (name, type) VALUES (?, 'grocery')", (store,)
                )
                list_id = cursor.lastrowid
            else:
                list_id = row[0]

            cursor = await db.execute(
                "INSERT INTO list_items (list_id, text, quantity) VALUES (?, ?, ?)",
                (list_id, item, quantity),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "store": store, "item": item, "quantity": quantity}
        finally:
            await db.close()

    async def get_list(self, store: str | None = None) -> list[dict]:
        db = await self.storage.connect()
        try:
            if store:
                cursor = await db.execute(
                    "SELECT li.id, l.name AS store, li.text, li.quantity, li.done "
                    "FROM list_items li JOIN lists l ON li.list_id = l.id "
                    "WHERE l.type = 'grocery' AND l.name = ? "
                    "ORDER BY li.done, li.created_at",
                    (store,),
                )
            else:
                cursor = await db.execute(
                    "SELECT li.id, l.name AS store, li.text, li.quantity, li.done "
                    "FROM list_items li JOIN lists l ON li.list_id = l.id "
                    "WHERE l.type = 'grocery' "
                    "ORDER BY l.name, li.done, li.created_at"
                )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "store": r[1], "text": r[2], "quantity": r[3], "done": bool(r[4])}
                for r in rows
            ]
        finally:
            await db.close()

    async def remove_item(self, item_id: int) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def check_item(self, item_id: int, done: bool = True) -> bool:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "UPDATE list_items SET done = ? WHERE id = ?", (int(done), item_id)
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    async def clear_done(self, store: str | None = None) -> int:
        db = await self.storage.connect()
        try:
            if store:
                cursor = await db.execute(
                    "DELETE FROM list_items WHERE done = 1 AND list_id IN "
                    "(SELECT id FROM lists WHERE name = ? AND type = 'grocery')",
                    (store,),
                )
            else:
                cursor = await db.execute(
                    "DELETE FROM list_items WHERE done = 1 AND list_id IN "
                    "(SELECT id FROM lists WHERE type = 'grocery')"
                )
            await db.commit()
            return cursor.rowcount
        finally:
            await db.close()

    async def health_check(self) -> dict:
        items = await self.get_list()
        return {"healthy": True, "details": f"{len(items)} grocery items"}
