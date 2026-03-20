from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..brain.agent import Agent
from ..config import Settings
from ..services.base import ServiceRegistry
from .middleware import APIKeyMiddleware

STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[*] Initializing services...")
    await app.state.registry.initialize_all()
    health = await app.state.registry.health_check_all()
    for name, status in health.items():
        marker = "+" if status["healthy"] else "-"
        print(f"  [{marker}] {name}: {status['details']}")
    print(f"[+] {app.state.settings.assistant_name} is ready")
    yield
    print("[*] Shutting down...")


def create_app(registry: ServiceRegistry, agent: Agent, settings: Settings) -> FastAPI:
    app = FastAPI(title=settings.assistant_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(APIKeyMiddleware, api_key=settings.api_key)
    app.state.registry = registry
    app.state.agent = agent
    app.state.settings = settings

    from .routes_assistant import router as assistant_router
    from .routes_pico import router as pico_router
    from .routes_health import router as health_router
    from .routes_kiosk import router as kiosk_router
    from .routes_hooks import router as hooks_router

    app.include_router(assistant_router, prefix="/api")
    app.include_router(pico_router, prefix="/api/pico")
    app.include_router(health_router, prefix="/api")
    app.include_router(kiosk_router, prefix="/api")
    app.include_router(hooks_router, prefix="/api/hooks")

    # Serve static JS/CSS files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    return app
