import pytest
import pytest_asyncio
from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.grocery import GroceryService


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
