from __future__ import annotations

import asyncio
import time

from .base import BaseService


class TimerEntry:
    def __init__(self, name: str, duration: int, task: asyncio.Task):
        self.name = name
        self.duration = duration
        self.started_at = time.time()
        self.task = task
        self.fired = False

    @property
    def remaining(self) -> float:
        if self.fired:
            return 0
        left = self.duration - (time.time() - self.started_at)
        return max(0, left)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration": self.duration,
            "remaining": round(self.remaining),
            "fired": self.fired,
        }


class TimerService(BaseService):
    """In-memory cooking timers using asyncio tasks."""

    name = "timers"

    def __init__(self):
        self._timers: dict[str, TimerEntry] = {}
        self._fired_events: list[dict] = []

    async def set_timer(self, name: str, seconds: int) -> dict:
        # Cancel existing timer with same name
        if name in self._timers:
            self._timers[name].task.cancel()

        task = asyncio.create_task(self._run_timer(name, seconds))
        entry = TimerEntry(name, seconds, task)
        self._timers[name] = entry
        return entry.to_dict()

    async def list_timers(self) -> list[dict]:
        # Clean up fired timers older than 5 minutes
        cutoff = time.time() - 300
        to_remove = [
            n for n, t in self._timers.items()
            if t.fired and t.started_at + t.duration < cutoff
        ]
        for n in to_remove:
            del self._timers[n]

        return [t.to_dict() for t in self._timers.values()]

    async def cancel_timer(self, name: str) -> bool:
        entry = self._timers.pop(name, None)
        if entry:
            entry.task.cancel()
            return True
        return False

    def get_fired_events(self) -> list[dict]:
        events = self._fired_events[:]
        self._fired_events.clear()
        return events

    async def _run_timer(self, name: str, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            entry = self._timers.get(name)
            if entry:
                entry.fired = True
                self._fired_events.append({
                    "name": name,
                    "fired_at": time.time(),
                })
        except asyncio.CancelledError:
            pass

    async def health_check(self) -> dict:
        active = sum(1 for t in self._timers.values() if not t.fired)
        return {"healthy": True, "details": f"{active} active timers"}
