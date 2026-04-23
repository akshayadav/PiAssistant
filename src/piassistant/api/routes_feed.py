from __future__ import annotations

import hmac

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse

router = APIRouter()


def _ok_password(request: Request, token: str) -> bool:
    settings = request.app.state.settings
    if not settings.feed_password:
        return False
    return hmac.compare_digest(token, settings.feed_password)


@router.get("/feed/status")
async def feed_status(request: Request):
    """Whether the camera feed is configured (URL set and password set)."""
    settings = request.app.state.settings
    camera = request.app.state.registry.get("camera")
    return {
        "configured": bool(settings.jetson_camera_url and settings.feed_password),
        "reachable": (await camera.health_check())["healthy"] if camera.configured else False,
    }


@router.get("/feed/snapshot")
async def feed_snapshot(request: Request, token: str = Query(default="")):
    if not _ok_password(request, token):
        return Response(status_code=401, content=b"unauthorized")
    camera = request.app.state.registry.get("camera")
    if not camera.configured:
        return Response(status_code=503, content=b"camera not configured")
    try:
        content, content_type = await camera.snapshot()
    except Exception as e:
        return Response(status_code=502, content=f"upstream error: {e}".encode())
    return Response(content=content, media_type=content_type)


@router.get("/feed/stream")
async def feed_stream(request: Request, token: str = Query(default="")):
    if not _ok_password(request, token):
        return Response(status_code=401, content=b"unauthorized")
    camera = request.app.state.registry.get("camera")
    if not camera.configured:
        return Response(status_code=503, content=b"camera not configured")

    # Peek the first yield to learn the upstream Content-Type (boundary must
    # match), then wrap the rest as the body.
    stream_gen = camera.stream_iter()
    try:
        first_chunk, content_type = await anext(stream_gen)
    except StopAsyncIteration:
        return Response(status_code=502, content=b"upstream closed")
    except Exception as e:
        return Response(status_code=502, content=f"upstream error: {e}".encode())

    async def body():
        if first_chunk:
            yield first_chunk
        async for chunk, _ct in stream_gen:
            yield chunk

    return StreamingResponse(body(), media_type=content_type)
