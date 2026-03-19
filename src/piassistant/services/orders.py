from __future__ import annotations

import asyncio
import json
import logging
import time

from ..config import Settings
from .base import BaseService
from .storage import StorageService

logger = logging.getLogger(__name__)


class AmazonOrdersService(BaseService):
    """Amazon order tracking backed by SQLite, refreshed via amazon-orders library."""

    name = "orders"

    def __init__(self, storage: StorageService, settings: Settings):
        self.storage = storage
        self.settings = settings
        self._last_refresh: float = 0
        self._refresh_lock = asyncio.Lock()
        self._bg_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        # Create table via migration (schema may not exist yet)
        db = await self.storage.connect()
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS amazon_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    order_date TEXT NOT NULL,
                    grand_total REAL,
                    delivery_status TEXT DEFAULT '',
                    tracking_link TEXT DEFAULT '',
                    items_json TEXT DEFAULT '[]',
                    is_delivered INTEGER DEFAULT 0,
                    last_updated TEXT DEFAULT (datetime('now'))
                );
                """
            )
            await db.commit()
        finally:
            await db.close()

        if self.settings.amazon_email and self.settings.amazon_password:
            self._bg_task = asyncio.create_task(self._background_refresh_loop())

    async def _background_refresh_loop(self) -> None:
        """Periodically refresh orders from Amazon."""
        while True:
            try:
                await self._do_refresh()
            except Exception as e:
                logger.warning("Background order refresh failed: %s", e)
            await asyncio.sleep(self.settings.amazon_refresh_interval)

    async def _do_refresh(self) -> None:
        """Fetch orders from Amazon and store them."""
        async with self._refresh_lock:
            now = time.time()
            if now - self._last_refresh < self.settings.amazon_min_refresh_gap:
                logger.info("Order refresh skipped — too soon (min gap %ds)", self.settings.amazon_min_refresh_gap)
                return

            logger.info("Refreshing Amazon orders...")
            orders = await asyncio.to_thread(self._fetch_from_amazon)
            if orders:
                await self._store_orders(orders)
            self._last_refresh = time.time()
            logger.info("Amazon orders refreshed: %d orders fetched", len(orders))

    def _fetch_from_amazon(self) -> list[dict]:
        """Sync method: log into Amazon and fetch recent orders."""
        try:
            from amazonorders.session import AmazonSession
            from amazonorders.orders import AmazonOrders
        except ImportError:
            logger.error("amazon-orders library not installed — pip install amazon-orders")
            return []

        try:
            session = AmazonSession(
                self.settings.amazon_email,
                self.settings.amazon_password,
                otp_secret=self.settings.amazon_otp_secret or None,
            )
            session.login()

            amazon_orders = AmazonOrders(session)
            orders = amazon_orders.get_order_history(time_filter="Last30Days")

            result = []
            for order in orders:
                items = []
                for item in order.items:
                    items.append({
                        "title": item.title or "",
                        "link": item.link or "",
                        "price": None,
                        "image_link": getattr(item, "image_link", "") or "",
                        "quantity": getattr(item, "quantity", 1),
                    })

                shipments = order.shipments or []
                delivery_status = ""
                tracking_link = ""
                is_delivered = False

                for shipment in shipments:
                    status = getattr(shipment, "delivery_status", "") or ""
                    if status:
                        delivery_status = status
                    link = getattr(shipment, "tracking_link", "") or ""
                    if link:
                        tracking_link = link
                    if "delivered" in status.lower():
                        is_delivered = True

                # If no shipments, check order-level status
                if not shipments:
                    order_status = getattr(order, "order_status", "") or ""
                    delivery_status = order_status
                    if "delivered" in order_status.lower():
                        is_delivered = True

                result.append({
                    "order_number": order.order_number or "",
                    "order_date": str(order.order_placed_date or ""),
                    "grand_total": order.grand_total,
                    "delivery_status": delivery_status,
                    "tracking_link": tracking_link,
                    "items": items,
                    "is_delivered": is_delivered,
                })
            return result

        except Exception as e:
            logger.error("Amazon order fetch failed: %s", e)
            return []

    async def _store_orders(self, orders: list[dict]) -> None:
        """Upsert orders into SQLite."""
        db = await self.storage.connect()
        try:
            for order in orders:
                await db.execute(
                    """
                    INSERT INTO amazon_orders (order_number, order_date, grand_total,
                        delivery_status, tracking_link, items_json, is_delivered, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(order_number) DO UPDATE SET
                        delivery_status = excluded.delivery_status,
                        tracking_link = excluded.tracking_link,
                        items_json = excluded.items_json,
                        is_delivered = excluded.is_delivered,
                        last_updated = datetime('now')
                    """,
                    (
                        order["order_number"],
                        order["order_date"],
                        order.get("grand_total"),
                        order.get("delivery_status", ""),
                        order.get("tracking_link", ""),
                        json.dumps(order.get("items", [])),
                        int(order.get("is_delivered", False)),
                    ),
                )
            await db.commit()
        finally:
            await db.close()

    async def get_undelivered(self) -> list[dict]:
        """Get orders that haven't been delivered yet."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT order_number, order_date, grand_total, delivery_status, "
                "tracking_link, items_json FROM amazon_orders "
                "WHERE is_delivered = 0 ORDER BY order_date DESC"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "order_number": r[0],
                    "order_date": r[1],
                    "grand_total": r[2],
                    "delivery_status": r[3],
                    "tracking_link": r[4],
                    "items": json.loads(r[5]),
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def get_all_recent(self) -> list[dict]:
        """Get all recent orders (delivered and undelivered)."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT order_number, order_date, grand_total, delivery_status, "
                "tracking_link, items_json, is_delivered FROM amazon_orders "
                "ORDER BY order_date DESC"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "order_number": r[0],
                    "order_date": r[1],
                    "grand_total": r[2],
                    "delivery_status": r[3],
                    "tracking_link": r[4],
                    "items": json.loads(r[5]),
                    "is_delivered": bool(r[6]),
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def force_refresh(self) -> dict:
        """Manually trigger a refresh. Returns status."""
        if not self.settings.amazon_email or not self.settings.amazon_password:
            return {"error": "Amazon credentials not configured. Set AMAZON_EMAIL and AMAZON_PASSWORD in .env"}

        try:
            await self._do_refresh()
            orders = await self.get_undelivered()
            return {"refreshed": True, "undelivered_count": len(orders)}
        except Exception as e:
            return {"error": f"Refresh failed: {e}"}

    async def health_check(self) -> dict:
        configured = bool(self.settings.amazon_email and self.settings.amazon_password)
        try:
            orders = await self.get_undelivered()
            return {
                "healthy": True,
                "details": f"{len(orders)} undelivered orders, configured={configured}",
            }
        except Exception as e:
            return {"healthy": False, "details": str(e)}
