from __future__ import annotations

from .base import BaseService
from .storage import StorageService

# Legacy default stores (kept for backward compat with existing lists table rows)
DEFAULT_STORES = [
    "Whole Foods",
    "Sprouts",
    "Indian Grocery",
    "Costco",
    "Target",
    "Other",
]

STORE_CATEGORIES = [
    ("indian", "Indian Stores"),
    ("bulk", "Bulk / Warehouse"),
    ("regular", "Regular Grocery"),
    ("produce", "Produce & Meat"),
    ("online", "Online"),
]

DEFAULT_STORES_V2 = [
    ("New India Bazaar", "indian"),
    ("India Cash and Carry", "indian"),
    ("Apna Mandi", "indian"),
    ("Costco", "bulk"),
    ("Safeway", "regular"),
    ("Lucky", "regular"),
    ("Target", "regular"),
    ("Sprouts", "produce"),
    ("Whole Foods", "produce"),
    ("Amazon", "online"),
]

# Maps product keywords → store category for smart routing
ITEM_CATEGORY_HINTS: dict[str, str] = {
    # Indian stores
    "rice": "indian", "basmati": "indian", "jasmine rice": "indian",
    "spice": "indian", "spices": "indian", "dal": "indian", "daal": "indian",
    "masala": "indian", "garam masala": "indian", "ghee": "indian",
    "atta": "indian", "paneer": "indian", "chana": "indian",
    "turmeric": "indian", "cumin": "indian", "coriander": "indian",
    "curry": "indian", "naan": "indian", "roti": "indian",
    "pickle": "indian", "papad": "indian", "chutney": "indian",
    # Bulk / warehouse
    "san pellegrino": "bulk", "pellegrino": "bulk",
    "coconut water": "bulk", "olive oil": "bulk",
    "toilet paper": "bulk", "paper towel": "bulk", "paper towels": "bulk",
    "trash bag": "bulk", "trash bags": "bulk", "water bottles": "bulk",
    "laundry pods": "bulk", "batteries": "bulk", "ziploc": "bulk",
    # Regular grocery
    "toothpaste": "regular", "detergent": "regular", "soap": "regular",
    "shampoo": "regular", "dish soap": "regular", "sponge": "regular",
    "conditioner": "regular", "deodorant": "regular", "floss": "regular",
    "cereal": "regular", "bread": "regular", "pasta": "regular",
    # Produce & meat
    "fruit": "produce", "fruits": "produce", "vegetable": "produce",
    "vegetables": "produce", "veggies": "produce", "meat": "produce",
    "chicken": "produce", "salmon": "produce", "fish": "produce",
    "avocado": "produce", "berries": "produce", "salad": "produce",
    "organic": "produce", "apple": "produce", "banana": "produce",
    "tomato": "produce", "onion": "produce", "potato": "produce",
    "spinach": "produce", "kale": "produce", "broccoli": "produce",
}


class GroceryService(BaseService):
    """Grocery list management with smart store routing, product catalog, and price tracking."""

    name = "grocery"

    def __init__(self, storage: StorageService):
        self.storage = storage

    async def initialize(self) -> None:
        db = await self.storage.connect()
        try:
            # Seed legacy store lists (backward compat)
            for store in DEFAULT_STORES:
                await db.execute(
                    "INSERT OR IGNORE INTO lists (name, type) VALUES (?, 'grocery')",
                    (store,),
                )

            # Seed store categories
            for slug, display_name in STORE_CATEGORIES:
                await db.execute(
                    "INSERT OR IGNORE INTO store_categories (slug, display_name) VALUES (?, ?)",
                    (slug, display_name),
                )

            # Seed stores
            for store_name, cat_slug in DEFAULT_STORES_V2:
                await db.execute(
                    "INSERT OR IGNORE INTO stores (name, category_slug) VALUES (?, ?)",
                    (store_name, cat_slug),
                )
                # Also ensure a lists entry exists for each store
                await db.execute(
                    "INSERT OR IGNORE INTO lists (name, type) VALUES (?, 'grocery')",
                    (store_name,),
                )

            await db.commit()
        finally:
            await db.close()

    # ---- Original list methods (unchanged) ----

    async def add_item(
        self,
        store: str,
        item: str,
        quantity: str = "",
        price: float | None = None,
        brand: str = "",
        notes: str = "",
        product_id: int | None = None,
    ) -> dict:
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id FROM lists WHERE name = ? AND type = 'grocery'", (store,)
            )
            row = await cursor.fetchone()
            if not row:
                cursor = await db.execute(
                    "INSERT INTO lists (name, type) VALUES (?, 'grocery')", (store,)
                )
                list_id = cursor.lastrowid
            else:
                list_id = row[0]

            cursor = await db.execute(
                "INSERT INTO list_items (list_id, text, quantity, product_id, price, brand, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (list_id, item, quantity, product_id, price, brand, notes),
            )
            await db.commit()
            result = {
                "id": cursor.lastrowid,
                "store": store,
                "item": item,
                "quantity": quantity,
            }
            if price is not None:
                result["price"] = price
            if brand:
                result["brand"] = brand
            if notes:
                result["notes"] = notes
            return result
        finally:
            await db.close()

    async def get_list(self, store: str | None = None) -> list[dict]:
        db = await self.storage.connect()
        try:
            if store:
                cursor = await db.execute(
                    "SELECT li.id, l.name AS store, li.text, li.quantity, li.done, "
                    "li.price, li.brand, li.notes "
                    "FROM list_items li JOIN lists l ON li.list_id = l.id "
                    "WHERE l.type = 'grocery' AND l.name = ? "
                    "ORDER BY li.done, li.created_at",
                    (store,),
                )
            else:
                cursor = await db.execute(
                    "SELECT li.id, l.name AS store, li.text, li.quantity, li.done, "
                    "li.price, li.brand, li.notes "
                    "FROM list_items li JOIN lists l ON li.list_id = l.id "
                    "WHERE l.type = 'grocery' "
                    "ORDER BY l.name, li.done, li.created_at"
                )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "store": r[1],
                    "text": r[2],
                    "quantity": r[3],
                    "done": bool(r[4]),
                    "price": r[5],
                    "brand": r[6] if r[6] else None,
                    "notes": r[7] if r[7] else None,
                }
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

    # ---- Smart grocery methods ----

    async def get_stores(self, category: str | None = None) -> list[dict]:
        """List stores, optionally filtered by category slug."""
        db = await self.storage.connect()
        try:
            if category:
                cursor = await db.execute(
                    "SELECT s.id, s.name, s.category_slug, sc.display_name, s.location, s.notes "
                    "FROM stores s JOIN store_categories sc ON s.category_slug = sc.slug "
                    "WHERE s.active = 1 AND s.category_slug = ? "
                    "ORDER BY sc.display_name, s.name",
                    (category,),
                )
            else:
                cursor = await db.execute(
                    "SELECT s.id, s.name, s.category_slug, sc.display_name, s.location, s.notes "
                    "FROM stores s JOIN store_categories sc ON s.category_slug = sc.slug "
                    "WHERE s.active = 1 "
                    "ORDER BY sc.display_name, s.name"
                )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "category": r[2],
                    "category_name": r[3],
                    "location": r[4],
                    "notes": r[5],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def add_store(
        self, name: str, category_slug: str, location: str = "", notes: str = ""
    ) -> dict:
        """Register a new store."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO stores (name, category_slug, location, notes) "
                "VALUES (?, ?, ?, ?)",
                (name, category_slug, location, notes),
            )
            # Also ensure a lists entry for grocery_add compatibility
            await db.execute(
                "INSERT OR IGNORE INTO lists (name, type) VALUES (?, 'grocery')",
                (name,),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "name": name, "category": category_slug}
        finally:
            await db.close()

    async def get_or_create_product(
        self,
        name: str,
        category: str = "",
        brand: str = "",
        default_store_category: str = "",
        unit: str = "",
    ) -> dict:
        """Find an existing product by name or create a new one."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id, name, category, default_store_category, brand, unit, notes "
                "FROM products WHERE LOWER(name) = LOWER(?)",
                (name,),
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "name": row[1], "category": row[2],
                    "default_store_category": row[3], "brand": row[4],
                    "unit": row[5], "notes": row[6],
                }

            # Auto-detect store category from hints if not provided
            if not default_store_category:
                default_store_category = self._guess_store_category(name)

            cursor = await db.execute(
                "INSERT INTO products (name, category, default_store_category, brand, unit) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, category, default_store_category, brand, unit),
            )
            await db.commit()
            return {
                "id": cursor.lastrowid, "name": name, "category": category,
                "default_store_category": default_store_category, "brand": brand,
                "unit": unit, "notes": "",
            }
        finally:
            await db.close()

    async def search_products(self, query: str) -> list[dict]:
        """Fuzzy search the product catalog."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id, name, category, default_store_category, brand, unit, notes "
                "FROM products WHERE LOWER(name) LIKE ? ORDER BY name LIMIT 20",
                (f"%{query.lower()}%",),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "name": r[1], "category": r[2],
                    "default_store_category": r[3], "brand": r[4],
                    "unit": r[5], "notes": r[6],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def record_price(
        self,
        product_id: int,
        store_id: int,
        price: float,
        quantity: str = "",
        unit_price: float | None = None,
        source: str = "user",
        url: str = "",
    ) -> dict:
        """Record a price observation for a product at a store."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "INSERT INTO price_history "
                "(product_id, store_id, price, quantity, unit_price, source, url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (product_id, store_id, price, quantity, unit_price, source, url),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "product_id": product_id, "store_id": store_id, "price": price}
        finally:
            await db.close()

    async def get_price_history(
        self, product_id: int, store_id: int | None = None, limit: int = 10
    ) -> list[dict]:
        """Get recent price observations for a product."""
        db = await self.storage.connect()
        try:
            if store_id:
                cursor = await db.execute(
                    "SELECT ph.id, ph.price, ph.quantity, ph.unit_price, ph.source, "
                    "ph.observed_at, s.name AS store_name "
                    "FROM price_history ph JOIN stores s ON ph.store_id = s.id "
                    "WHERE ph.product_id = ? AND ph.store_id = ? "
                    "ORDER BY ph.observed_at DESC LIMIT ?",
                    (product_id, store_id, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT ph.id, ph.price, ph.quantity, ph.unit_price, ph.source, "
                    "ph.observed_at, s.name AS store_name "
                    "FROM price_history ph JOIN stores s ON ph.store_id = s.id "
                    "WHERE ph.product_id = ? "
                    "ORDER BY ph.observed_at DESC LIMIT ?",
                    (product_id, limit),
                )
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0], "price": r[1], "quantity": r[2],
                    "unit_price": r[3], "source": r[4],
                    "observed_at": r[5], "store": r[6],
                }
                for r in rows
            ]
        finally:
            await db.close()

    async def get_recommendation(self, product_name: str) -> dict:
        """Get smart recommendation for a product: category hint, known prices, preferences."""
        category_hint = self._guess_store_category(product_name)

        # Search for existing products
        products = await self.search_products(product_name)

        # Gather prices and preferences for matched products
        prices = []
        preferences = []
        for product in products:
            product_prices = await self.get_price_history(product["id"])
            prices.extend(product_prices)

            pref = await self._get_preference(product["id"])
            if pref:
                preferences.append(pref)

        # Get stores in the recommended category
        recommended_stores = []
        if category_hint:
            recommended_stores = await self.get_stores(category_hint)

        return {
            "product_name": product_name,
            "category_hint": category_hint,
            "category_name": dict(STORE_CATEGORIES).get(category_hint, ""),
            "matching_products": products,
            "recent_prices": prices,
            "preferences": preferences,
            "recommended_stores": recommended_stores,
        }

    async def set_preference(
        self,
        product_id: int,
        preferred_store_id: int | None = None,
        preferred_brand: str = "",
        notes: str = "",
    ) -> dict:
        """Save or update a user preference for a product."""
        db = await self.storage.connect()
        try:
            # Upsert: update if exists, insert if not
            cursor = await db.execute(
                "SELECT id FROM item_preferences WHERE product_id = ?", (product_id,)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE item_preferences SET preferred_store_id = ?, "
                    "preferred_brand = ?, notes = ?, updated_at = datetime('now') "
                    "WHERE product_id = ?",
                    (preferred_store_id, preferred_brand, notes, product_id),
                )
                pref_id = row[0]
            else:
                cursor = await db.execute(
                    "INSERT INTO item_preferences "
                    "(product_id, preferred_store_id, preferred_brand, notes) "
                    "VALUES (?, ?, ?, ?)",
                    (product_id, preferred_store_id, preferred_brand, notes),
                )
                pref_id = cursor.lastrowid
            await db.commit()

            # Return enriched result
            result = {"id": pref_id, "product_id": product_id}
            if preferred_store_id:
                store_cursor = await db.execute(
                    "SELECT name FROM stores WHERE id = ?", (preferred_store_id,)
                )
                store_row = await store_cursor.fetchone()
                if store_row:
                    result["preferred_store"] = store_row[0]
            if preferred_brand:
                result["preferred_brand"] = preferred_brand
            if notes:
                result["notes"] = notes
            return result
        finally:
            await db.close()

    async def get_store_id(self, store_name: str) -> int | None:
        """Look up a store ID by name."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id FROM stores WHERE LOWER(name) = LOWER(?)", (store_name,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None
        finally:
            await db.close()

    async def get_product_id(self, product_name: str) -> int | None:
        """Look up a product ID by name."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT id FROM products WHERE LOWER(name) = LOWER(?)", (product_name,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None
        finally:
            await db.close()

    # ---- Internal helpers ----

    @staticmethod
    def _guess_store_category(product_name: str) -> str:
        """Match product name against ITEM_CATEGORY_HINTS. Returns category slug or ''."""
        name_lower = product_name.lower()
        # Try exact match first, then substring match
        for keyword, category in ITEM_CATEGORY_HINTS.items():
            if keyword == name_lower:
                return category
        for keyword, category in ITEM_CATEGORY_HINTS.items():
            if keyword in name_lower or name_lower in keyword:
                return category
        return ""

    async def _get_preference(self, product_id: int) -> dict | None:
        """Get preference for a product."""
        db = await self.storage.connect()
        try:
            cursor = await db.execute(
                "SELECT ip.id, ip.preferred_store_id, ip.preferred_brand, ip.notes, "
                "s.name AS store_name "
                "FROM item_preferences ip LEFT JOIN stores s ON ip.preferred_store_id = s.id "
                "WHERE ip.product_id = ?",
                (product_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "preferred_store_id": row[1],
                "preferred_store": row[4],
                "preferred_brand": row[2],
                "notes": row[3],
            }
        finally:
            await db.close()

    async def health_check(self) -> dict:
        items = await self.get_list()
        return {"healthy": True, "details": f"{len(items)} grocery items"}
