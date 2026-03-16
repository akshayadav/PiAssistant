from __future__ import annotations

from abc import ABC, abstractmethod


class BaseService(ABC):
    """Base interface for all PiAssistant services."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    async def initialize(self) -> None:
        """Called once at startup. Override to validate config or test connections."""
        pass

    async def health_check(self) -> dict:
        """Return service health. Override for real checks."""
        return {"healthy": True, "details": "ok"}


class ServiceRegistry:
    """Simple dict-based registry for services."""

    def __init__(self):
        self._services: dict[str, BaseService] = {}

    def register(self, service: BaseService) -> None:
        self._services[service.name] = service

    def get(self, name: str) -> BaseService:
        service = self._services.get(name)
        if service is None:
            raise KeyError(f"Service '{name}' not registered")
        return service

    async def initialize_all(self) -> None:
        for service in self._services.values():
            await service.initialize()

    async def health_check_all(self) -> dict:
        results = {}
        for name, service in self._services.items():
            try:
                results[name] = await service.health_check()
            except Exception as e:
                results[name] = {"healthy": False, "details": str(e)}
        return results
