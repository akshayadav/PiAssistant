import asyncio
import subprocess

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    """Service health check for diagnostics."""
    registry = request.app.state.registry
    checks = await registry.health_check_all()
    all_healthy = all(c["healthy"] for c in checks.values())
    return {
        "status": "ok" if all_healthy else "degraded",
        "services": checks,
    }


@router.post("/shutdown")
async def shutdown():
    """Safely shut down the Raspberry Pi."""
    # Give time for the HTTP response to be sent before shutdown
    asyncio.get_event_loop().call_later(
        2, lambda: subprocess.run(["sudo", "shutdown", "-h", "now"])
    )
    return {"status": "shutting_down"}
