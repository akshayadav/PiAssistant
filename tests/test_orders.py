import pytest
import pytest_asyncio
from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.orders import AmazonOrdersService


@pytest_asyncio.fixture
async def orders(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "test.db"),
        anthropic_api_key="test",
        amazon_email="",
        amazon_password="",
    )
    storage = StorageService(settings)
    await storage.initialize()
    svc = AmazonOrdersService(storage, settings)
    await svc.initialize()
    return svc


SAMPLE_ORDERS = [
    {
        "order_number": "111-0000001",
        "order_date": "2026-03-15",
        "grand_total": 29.99,
        "delivery_status": "Shipped",
        "tracking_link": "https://track.example.com/1",
        "items": [{"title": "USB-C Cable", "price": 9.99, "image_link": "", "quantity": 1}],
        "is_delivered": False,
    },
    {
        "order_number": "111-0000002",
        "order_date": "2026-03-10",
        "grand_total": 55.00,
        "delivery_status": "Delivered",
        "tracking_link": "",
        "items": [{"title": "Raspberry Pi Case", "price": 25.00, "image_link": "", "quantity": 1}],
        "is_delivered": True,
    },
    {
        "order_number": "111-0000003",
        "order_date": "2026-03-16",
        "grand_total": 12.50,
        "delivery_status": "Out for delivery",
        "tracking_link": "https://track.example.com/3",
        "items": [
            {"title": "SD Card 64GB", "price": 8.50, "image_link": "", "quantity": 1},
            {"title": "SD Card Reader", "price": 4.00, "image_link": "", "quantity": 1},
        ],
        "is_delivered": False,
    },
]


class TestAmazonOrdersService:
    @pytest.mark.asyncio
    async def test_store_and_get_undelivered(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)
        undelivered = await orders.get_undelivered()
        assert len(undelivered) == 2
        numbers = {o["order_number"] for o in undelivered}
        assert numbers == {"111-0000001", "111-0000003"}

    @pytest.mark.asyncio
    async def test_delivered_filtered(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)
        undelivered = await orders.get_undelivered()
        for o in undelivered:
            assert o["order_number"] != "111-0000002"

    @pytest.mark.asyncio
    async def test_get_all_recent(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)
        all_orders = await orders.get_all_recent()
        assert len(all_orders) == 3

    @pytest.mark.asyncio
    async def test_upsert_updates_status(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)

        # Update order 1 to delivered
        updated = [{
            "order_number": "111-0000001",
            "order_date": "2026-03-15",
            "grand_total": 29.99,
            "delivery_status": "Delivered March 17",
            "tracking_link": "https://track.example.com/1",
            "items": [{"title": "USB-C Cable", "price": 9.99, "image_link": "", "quantity": 1}],
            "is_delivered": True,
        }]
        await orders._store_orders(updated)

        undelivered = await orders.get_undelivered()
        assert len(undelivered) == 1
        assert undelivered[0]["order_number"] == "111-0000003"

    @pytest.mark.asyncio
    async def test_items_json_parsed(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)
        undelivered = await orders.get_undelivered()
        multi_item = next(o for o in undelivered if o["order_number"] == "111-0000003")
        assert len(multi_item["items"]) == 2
        assert multi_item["items"][0]["title"] == "SD Card 64GB"

    @pytest.mark.asyncio
    async def test_force_refresh_no_credentials(self, orders):
        result = await orders.force_refresh()
        assert "error" in result
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check(self, orders):
        await orders._store_orders(SAMPLE_ORDERS)
        health = await orders.health_check()
        assert health["healthy"] is True
        assert "2 undelivered" in health["details"]
        assert "configured=False" in health["details"]

    @pytest.mark.asyncio
    async def test_empty_state(self, orders):
        undelivered = await orders.get_undelivered()
        assert undelivered == []
        health = await orders.health_check()
        assert health["healthy"] is True
