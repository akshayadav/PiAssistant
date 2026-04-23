from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from ..config import Settings
from .base import BaseService

logger = logging.getLogger(__name__)


class CameraService(BaseService):
    """Proxies the Jetson MJPEG camera service.

    The Jetson runs `deploy/jetson-camera/camera_service.py` on the LAN.
    This service fetches the MJPEG stream (or a snapshot) and streams it
    back to the dashboard. Auth is enforced by the Feed route, not here.
    """

    name = "camera"

    def __init__(self, settings: Settings):
        self.url = settings.jetson_camera_url.rstrip("/") if settings.jetson_camera_url else ""

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def initialize(self) -> None:
        if not self.configured:
            logger.info("Camera feed not configured (jetson_camera_url empty)")

    async def health_check(self) -> dict:
        if not self.configured:
            return {"healthy": True, "details": "not configured"}
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self.url}/health")
                r.raise_for_status()
                data = r.json()
            return {"healthy": True, "details": f"frames={data.get('frame_id', 0)}"}
        except Exception as e:
            return {"healthy": False, "details": f"{type(e).__name__}: {e}"}

    async def snapshot(self) -> tuple[bytes, str]:
        """Fetch the latest single JPEG. Returns (bytes, content-type)."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{self.url}/snapshot.jpg")
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "image/jpeg")

    async def stream_iter(self) -> AsyncIterator[tuple[bytes, str]]:
        """Open a long-lived MJPEG stream from the Jetson.

        Yields (chunk, content_type) tuples — the first yield carries the
        upstream Content-Type header so the caller can forward it verbatim
        (the boundary must match). Remaining yields are raw bytes.
        """
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0))
        try:
            async with client.stream("GET", f"{self.url}/stream.mjpg") as r:
                r.raise_for_status()
                ct = r.headers.get("content-type", "multipart/x-mixed-replace; boundary=jetsonmjpeg")
                yield b"", ct
                async for chunk in r.aiter_raw():
                    if chunk:
                        yield chunk, ct
        finally:
            await client.aclose()
