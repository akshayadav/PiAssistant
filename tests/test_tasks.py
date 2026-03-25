import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from piassistant.config import Settings
from piassistant.services.storage import StorageService
from piassistant.services.todo import TaskService


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(
        db_path=str(tmp_path / "test.db"),
        anthropic_api_key="test",
        stale_task_days=3,
        stale_check_interval=300,
    )


@pytest_asyncio.fixture
async def storage(tmp_settings):
    svc = StorageService(tmp_settings)
    await svc.initialize()
    return svc


@pytest_asyncio.fixture
async def task_service(storage, tmp_settings):
    svc = TaskService(storage, tmp_settings)
    # Initialize without starting the background stale checker
    await svc._migrate_legacy_data()
    return svc


class TestTaskService:
    @pytest.mark.asyncio
    async def test_add_task(self, task_service):
        result = await task_service.add_task(text="Buy milk")
        assert result["id"] is not None
        assert result["text"] == "Buy milk"
        assert result["priority"] == ""
        assert result["is_reminder"] is False

    @pytest.mark.asyncio
    async def test_add_task_with_priority_and_due_date(self, task_service):
        result = await task_service.add_task(
            text="Submit report", priority="high", due_at="2026-04-01T10:00"
        )
        assert result["priority"] == "high"
        assert result["due_at"] == "2026-04-01T10:00"

    @pytest.mark.asyncio
    async def test_add_reminder(self, task_service):
        result = await task_service.add_task(
            text="Call mom", is_reminder=True, for_person="Akshay"
        )
        assert result["is_reminder"] is True
        assert result["for_person"] == "Akshay"

    @pytest.mark.asyncio
    async def test_get_tasks_excludes_done(self, task_service):
        await task_service.add_task(text="Task 1")
        t2 = await task_service.add_task(text="Task 2")
        await task_service.complete_task(t2["id"])

        tasks = await task_service.get_tasks(include_done=False)
        assert len(tasks) == 1
        assert tasks[0]["text"] == "Task 1"

    @pytest.mark.asyncio
    async def test_get_tasks_includes_done(self, task_service):
        await task_service.add_task(text="Task 1")
        t2 = await task_service.add_task(text="Task 2")
        await task_service.complete_task(t2["id"])

        tasks = await task_service.get_tasks(include_done=True)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_get_tasks_sorted_by_urgency(self, task_service):
        # Low priority, no due date
        await task_service.add_task(text="Low task", priority="low")
        # High priority, no due date
        await task_service.add_task(text="High task", priority="high")
        # Overdue task
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        await task_service.add_task(text="Overdue task", priority="medium", due_at=past)

        tasks = await task_service.get_tasks()
        assert tasks[0]["text"] == "Overdue task"  # overdue comes first
        assert tasks[1]["text"] == "High task"  # then high priority
        assert tasks[2]["text"] == "Low task"  # then low priority

    @pytest.mark.asyncio
    async def test_complete_task(self, task_service):
        t = await task_service.add_task(text="Test task")
        result = await task_service.complete_task(t["id"])
        assert result is True

        task = await task_service.get_task(t["id"])
        assert task["done"] is True
        assert task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_nonexistent_task(self, task_service):
        result = await task_service.complete_task(9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_task(self, task_service):
        t = await task_service.add_task(text="Delete me")
        result = await task_service.delete_task(t["id"])
        assert result is True

        task = await task_service.get_task(t["id"])
        assert task is None

    @pytest.mark.asyncio
    async def test_update_task(self, task_service):
        t = await task_service.add_task(text="Original", priority="low")
        updated = await task_service.update_task(t["id"], priority="high", due_at="2026-05-01T09:00")

        assert updated["priority"] == "high"
        assert updated["due_at"] == "2026-05-01T09:00"
        assert updated["text"] == "Original"  # text unchanged

    @pytest.mark.asyncio
    async def test_update_task_text(self, task_service):
        t = await task_service.add_task(text="Old text")
        updated = await task_service.update_task(t["id"], text="New text")
        assert updated["text"] == "New text"

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, task_service):
        result = await task_service.update_task(9999, priority="high")
        assert result is None

    @pytest.mark.asyncio
    async def test_stale_detection_overdue(self, task_service):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        await task_service.add_task(text="Overdue item", due_at=past)

        await task_service._refresh_nudges()
        nudges = task_service.get_nudges()
        assert len(nudges) == 1
        assert nudges[0]["reason"] == "overdue"
        assert nudges[0]["text"] == "Overdue item"

    @pytest.mark.asyncio
    async def test_stale_detection_old_no_date(self, task_service):
        # Manually insert an old task
        db = await task_service.storage.connect()
        try:
            old_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
            await db.execute(
                "INSERT INTO tasks (text, priority, due_at, created_at) VALUES (?, '', '', ?)",
                ("Old task", old_date),
            )
            await db.commit()
        finally:
            await db.close()

        await task_service._refresh_nudges()
        nudges = task_service.get_nudges()
        assert len(nudges) == 1
        assert nudges[0]["reason"] == "needs attention"

    @pytest.mark.asyncio
    async def test_stale_detection_recent_not_flagged(self, task_service):
        await task_service.add_task(text="Fresh task")

        await task_service._refresh_nudges()
        nudges = task_service.get_nudges()
        assert len(nudges) == 0

    @pytest.mark.asyncio
    async def test_get_task(self, task_service):
        t = await task_service.add_task(text="Find me", priority="medium")
        found = await task_service.get_task(t["id"])
        assert found is not None
        assert found["text"] == "Find me"
        assert found["priority"] == "medium"

    @pytest.mark.asyncio
    async def test_get_task_nonexistent(self, task_service):
        result = await task_service.get_task(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check(self, task_service):
        await task_service.add_task(text="Task 1")
        await task_service.add_task(text="Task 2")
        health = await task_service.health_check()
        assert health["healthy"] is True
        assert "2 active tasks" in health["details"]

    @pytest.mark.asyncio
    async def test_data_migration(self, storage, tmp_settings):
        """Test that legacy todos and reminders are migrated to tasks table."""
        # Seed legacy data
        db = await storage.connect()
        try:
            await db.execute(
                "INSERT INTO lists (name, type) VALUES ('Todo', 'todo')"
            )
            await db.execute(
                "INSERT INTO list_items (list_id, text, quantity) VALUES (1, 'Legacy todo', 'high')"
            )
            await db.execute(
                "INSERT INTO reminders (text, due_at, for_person) VALUES ('Legacy reminder', '2026-04-01T10:00', 'Akshay')"
            )
            await db.commit()
        finally:
            await db.close()

        # Create TaskService and run migration
        svc = TaskService(storage, tmp_settings)
        await svc._migrate_legacy_data()

        tasks = await svc.get_tasks()
        assert len(tasks) == 2

        # Check migrated todo
        todo = next(t for t in tasks if t["text"] == "Legacy todo")
        assert todo["priority"] == "high"
        assert todo["is_reminder"] is False

        # Check migrated reminder
        reminder = next(t for t in tasks if t["text"] == "Legacy reminder")
        assert reminder["is_reminder"] is True
        assert reminder["for_person"] == "Akshay"
        assert reminder["due_at"] == "2026-04-01T10:00"
