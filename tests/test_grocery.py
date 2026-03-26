import pytest
import pytest_asyncio
from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.grocery import GroceryService, STORE_CATEGORIES, DEFAULT_STORES_V2, ITEM_CATEGORY_HINTS


@pytest_asyncio.fixture
async def grocery(tmp_path):
    settings = Settings(db_path=str(tmp_path / "test.db"), anthropic_api_key="test")
    storage = StorageService(settings)
    await storage.initialize()
    svc = GroceryService(storage)
    await svc.initialize()
    return svc


class TestGroceryService:
    @pytest.mark.asyncio
    async def test_default_stores_seeded(self, grocery):
        # Adding to a default store should work without creating it
        result = await grocery.add_item("Whole Foods", "milk")
        assert result["store"] == "Whole Foods"
        assert result["item"] == "milk"

    @pytest.mark.asyncio
    async def test_add_and_get(self, grocery):
        await grocery.add_item("Costco", "eggs", "2 dozen")
        await grocery.add_item("Costco", "bread")
        items = await grocery.get_list(store="Costco")
        assert len(items) == 2
        assert items[0]["text"] == "eggs"
        assert items[0]["quantity"] == "2 dozen"

    @pytest.mark.asyncio
    async def test_get_all_stores(self, grocery):
        await grocery.add_item("Target", "soap")
        await grocery.add_item("Costco", "rice")
        items = await grocery.get_list()
        assert len(items) == 2
        stores = {i["store"] for i in items}
        assert stores == {"Target", "Costco"}

    @pytest.mark.asyncio
    async def test_remove_item(self, grocery):
        result = await grocery.add_item("Sprouts", "apples")
        removed = await grocery.remove_item(result["id"])
        assert removed is True
        items = await grocery.get_list(store="Sprouts")
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_check_and_clear_done(self, grocery):
        r1 = await grocery.add_item("Other", "item1")
        r2 = await grocery.add_item("Other", "item2")
        await grocery.check_item(r1["id"], done=True)

        items = await grocery.get_list(store="Other")
        done_items = [i for i in items if i["done"]]
        assert len(done_items) == 1

        cleared = await grocery.clear_done(store="Other")
        assert cleared == 1

        items = await grocery.get_list(store="Other")
        assert len(items) == 1
        assert items[0]["text"] == "item2"

    @pytest.mark.asyncio
    async def test_auto_create_store(self, grocery):
        result = await grocery.add_item("Trader Joes", "hummus")
        assert result["store"] == "Trader Joes"
        items = await grocery.get_list(store="Trader Joes")
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_health_check(self, grocery):
        await grocery.add_item("Target", "soap")
        health = await grocery.health_check()
        assert health["healthy"] is True
        assert "1 grocery items" in health["details"]


class TestSmartGrocery:
    """Tests for smart grocery features: stores, products, prices, preferences."""

    @pytest.mark.asyncio
    async def test_store_categories_seeded(self, grocery):
        stores = await grocery.get_stores()
        assert len(stores) >= len(DEFAULT_STORES_V2)
        categories = {s["category"] for s in stores}
        assert "indian" in categories
        assert "bulk" in categories
        assert "produce" in categories

    @pytest.mark.asyncio
    async def test_get_stores_by_category(self, grocery):
        indian_stores = await grocery.get_stores(category="indian")
        assert len(indian_stores) == 3
        names = {s["name"] for s in indian_stores}
        assert "New India Bazaar" in names
        assert "India Cash and Carry" in names
        assert "Apna Mandi" in names

    @pytest.mark.asyncio
    async def test_add_store(self, grocery):
        result = await grocery.add_store("Patel Brothers", "indian", location="Sunnyvale")
        assert result["name"] == "Patel Brothers"
        assert result["category"] == "indian"
        # Should appear in Indian stores list
        indian_stores = await grocery.get_stores(category="indian")
        names = {s["name"] for s in indian_stores}
        assert "Patel Brothers" in names

    @pytest.mark.asyncio
    async def test_get_or_create_product_new(self, grocery):
        product = await grocery.get_or_create_product("Basmati Rice", category="rice")
        assert product["name"] == "Basmati Rice"
        assert product["id"] is not None
        # Auto-detected store category from hints
        assert product["default_store_category"] == "indian"

    @pytest.mark.asyncio
    async def test_get_or_create_product_existing(self, grocery):
        p1 = await grocery.get_or_create_product("Basmati Rice")
        p2 = await grocery.get_or_create_product("Basmati Rice")
        assert p1["id"] == p2["id"]

    @pytest.mark.asyncio
    async def test_search_products(self, grocery):
        await grocery.get_or_create_product("Basmati Rice")
        await grocery.get_or_create_product("Jasmine Rice")
        await grocery.get_or_create_product("Olive Oil")
        results = await grocery.search_products("rice")
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert "Basmati Rice" in names
        assert "Jasmine Rice" in names

    @pytest.mark.asyncio
    async def test_record_and_get_price(self, grocery):
        product = await grocery.get_or_create_product("Basmati Rice")
        store_id = await grocery.get_store_id("New India Bazaar")
        assert store_id is not None

        result = await grocery.record_price(
            product_id=product["id"],
            store_id=store_id,
            price=12.99,
            quantity="10 lb bag",
            unit_price=1.30,
        )
        assert result["price"] == 12.99

        prices = await grocery.get_price_history(product["id"])
        assert len(prices) == 1
        assert prices[0]["price"] == 12.99
        assert prices[0]["store"] == "New India Bazaar"
        assert prices[0]["quantity"] == "10 lb bag"
        assert prices[0]["unit_price"] == 1.30

    @pytest.mark.asyncio
    async def test_price_history_multiple_stores(self, grocery):
        product = await grocery.get_or_create_product("Basmati Rice")
        nib_id = await grocery.get_store_id("New India Bazaar")
        costco_id = await grocery.get_store_id("Costco")

        await grocery.record_price(product["id"], nib_id, 12.99, "10 lb bag")
        await grocery.record_price(product["id"], costco_id, 15.99, "15 lb bag")

        all_prices = await grocery.get_price_history(product["id"])
        assert len(all_prices) == 2

        nib_prices = await grocery.get_price_history(product["id"], store_id=nib_id)
        assert len(nib_prices) == 1
        assert nib_prices[0]["store"] == "New India Bazaar"

    @pytest.mark.asyncio
    async def test_set_and_get_preference(self, grocery):
        product = await grocery.get_or_create_product("Basmati Rice")
        store_id = await grocery.get_store_id("India Cash and Carry")

        result = await grocery.set_preference(
            product_id=product["id"],
            preferred_store_id=store_id,
            preferred_brand="Daawat",
            notes="get the 20lb bag",
        )
        assert result["preferred_store"] == "India Cash and Carry"
        assert result["preferred_brand"] == "Daawat"

    @pytest.mark.asyncio
    async def test_preference_upsert(self, grocery):
        product = await grocery.get_or_create_product("Basmati Rice")
        store1_id = await grocery.get_store_id("India Cash and Carry")
        store2_id = await grocery.get_store_id("New India Bazaar")

        await grocery.set_preference(product["id"], store1_id, "Daawat")
        result = await grocery.set_preference(product["id"], store2_id, "Lal Qilla")
        assert result["preferred_store"] == "New India Bazaar"
        assert result["preferred_brand"] == "Lal Qilla"

    @pytest.mark.asyncio
    async def test_get_recommendation(self, grocery):
        # Set up some data
        product = await grocery.get_or_create_product("Basmati Rice")
        store_id = await grocery.get_store_id("New India Bazaar")
        await grocery.record_price(product["id"], store_id, 12.99, "10 lb bag")
        await grocery.set_preference(product["id"], store_id, "Daawat")

        rec = await grocery.get_recommendation("rice")
        assert rec["category_hint"] == "indian"
        assert len(rec["matching_products"]) >= 1
        assert len(rec["recent_prices"]) >= 1
        assert len(rec["preferences"]) >= 1
        assert len(rec["recommended_stores"]) == 3  # 3 Indian stores

    @pytest.mark.asyncio
    async def test_get_recommendation_unknown_product(self, grocery):
        rec = await grocery.get_recommendation("toilet paper")
        assert rec["category_hint"] == "bulk"
        assert len(rec["matching_products"]) == 0
        assert len(rec["recent_prices"]) == 0
        # Should still recommend bulk stores
        assert len(rec["recommended_stores"]) >= 1

    @pytest.mark.asyncio
    async def test_guess_store_category(self, grocery):
        assert grocery._guess_store_category("basmati rice") == "indian"
        assert grocery._guess_store_category("Toilet Paper") == "bulk"
        assert grocery._guess_store_category("toothpaste") == "regular"
        assert grocery._guess_store_category("chicken breast") == "produce"
        assert grocery._guess_store_category("unknown gadget") == ""

    @pytest.mark.asyncio
    async def test_add_item_with_price_and_brand(self, grocery):
        result = await grocery.add_item(
            "Costco", "Olive Oil", "2 pack", price=19.99, brand="Kirkland"
        )
        assert result["price"] == 19.99
        assert result["brand"] == "Kirkland"

        items = await grocery.get_list(store="Costco")
        assert len(items) == 1
        assert items[0]["price"] == 19.99
        assert items[0]["brand"] == "Kirkland"

    @pytest.mark.asyncio
    async def test_get_list_includes_new_fields(self, grocery):
        await grocery.add_item("Safeway", "Toothpaste", notes="mint flavor")
        items = await grocery.get_list(store="Safeway")
        assert len(items) == 1
        assert items[0]["notes"] == "mint flavor"

    @pytest.mark.asyncio
    async def test_get_store_id(self, grocery):
        store_id = await grocery.get_store_id("Costco")
        assert store_id is not None
        assert await grocery.get_store_id("Nonexistent Store") is None

    @pytest.mark.asyncio
    async def test_get_product_id(self, grocery):
        await grocery.get_or_create_product("Olive Oil")
        pid = await grocery.get_product_id("Olive Oil")
        assert pid is not None
        assert await grocery.get_product_id("Nonexistent") is None
