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
