#!/usr/bin/env python3
"""Jetson IMX219 MJPEG streaming service.

Runs one GStreamer pipeline (nvarguscamerasrc → nvvidconv → jpegenc → appsink)
and fans out the latest JPEG to any number of HTTP clients via
multipart/x-mixed-replace. LAN-only by design — Bunty (PiAssistant) on the Pi
proxies it publicly and handles auth.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from fastapi import FastAPI, Response  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
import uvicorn  # noqa: E402

Gst.init(None)

log = logging.getLogger("jetson-camera")

WIDTH = int(os.getenv("CAMERA_WIDTH", "1280"))
HEIGHT = int(os.getenv("CAMERA_HEIGHT", "720"))
FRAMERATE = int(os.getenv("CAMERA_FRAMERATE", "30"))
QUALITY = int(os.getenv("CAMERA_QUALITY", "80"))
FLIP = int(os.getenv("CAMERA_FLIP", "0"))
PORT = int(os.getenv("CAMERA_PORT", "8001"))
BOUNDARY = "jetsonmjpeg"


class CameraBroadcaster:
    def __init__(self) -> None:
        self.latest_jpeg: bytes | None = None
        self.frame_id: int = 0
        self._subscribers: set[asyncio.Event] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._glib_loop: GLib.MainLoop | None = None

        pipeline_desc = (
            "nvarguscamerasrc ! "
            f"video/x-raw(memory:NVMM),width={WIDTH},height={HEIGHT},framerate={FRAMERATE}/1 ! "
            f"nvvidconv flip-method={FLIP} ! "
            "video/x-raw,format=I420 ! "
            f"jpegenc quality={QUALITY} ! "
            "appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false"
        )
        log.info("pipeline: %s", pipeline_desc)
        self._pipeline = Gst.parse_launch(pipeline_desc)
        appsink = self._pipeline.get_by_name("sink")
        appsink.connect("new-sample", self._on_new_sample)

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)

    def _on_new_sample(self, sink) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK
        try:
            jpeg = bytes(mapinfo.data)
        finally:
            buf.unmap(mapinfo)
        self.latest_jpeg = jpeg
        self.frame_id += 1
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._notify_subscribers)
        return Gst.FlowReturn.OK

    def _on_bus_error(self, _bus, msg) -> None:
        err, dbg = msg.parse_error()
        log.error("GStreamer error: %s (%s)", err, dbg)

    def _notify_subscribers(self) -> None:
        for ev in self._subscribers:
            ev.set()

    def subscribe(self) -> asyncio.Event:
        ev = asyncio.Event()
        self._subscribers.add(ev)
        return ev

    def unsubscribe(self, ev: asyncio.Event) -> None:
        self._subscribers.discard(ev)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._glib_loop = GLib.MainLoop()
        threading.Thread(target=self._glib_loop.run, daemon=True, name="glib-main").start()
        self._pipeline.set_state(Gst.State.PLAYING)
        log.info("camera pipeline started (%dx%d @ %d fps, q=%d)", WIDTH, HEIGHT, FRAMERATE, QUALITY)

    def stop(self) -> None:
        log.info("stopping camera pipeline")
        self._pipeline.set_state(Gst.State.NULL)
        if self._glib_loop is not None:
            self._glib_loop.quit()


camera = CameraBroadcaster()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    camera.start(asyncio.get_running_loop())
    yield
    camera.stop()


app = FastAPI(lifespan=lifespan, title="Jetson Camera")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "has_frame": camera.latest_jpeg is not None,
        "frame_id": camera.frame_id,
        "width": WIDTH,
        "height": HEIGHT,
        "framerate": FRAMERATE,
    }


@app.get("/snapshot.jpg")
def snapshot() -> Response:
    if camera.latest_jpeg is None:
        return Response(status_code=503)
    return Response(content=camera.latest_jpeg, media_type="image/jpeg")


async def _mjpeg_generator() -> AsyncIterator[bytes]:
    ev = camera.subscribe()
    try:
        last_id = -1
        while True:
            await ev.wait()
            ev.clear()
            jpeg = camera.latest_jpeg
            fid = camera.frame_id
            if jpeg is None or fid == last_id:
                continue
            last_id = fid
            header = (
                f"--{BOUNDARY}\r\n"
                f"Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n\r\n"
            ).encode("ascii")
            yield header + jpeg + b"\r\n"
    finally:
        camera.unsubscribe(ev)


@app.get("/stream.mjpg")
async def stream() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
