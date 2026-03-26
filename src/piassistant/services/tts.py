from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time

import httpx

from ..config import Settings
from .base import BaseService

logger = logging.getLogger(__name__)


class TTSUnavailableError(Exception):
    """Raised when no TTS backend is available."""


class TTSService(BaseService):
    """Text-to-speech via Kokoro (Mac Mini) with Piper fallback (Pi local)."""

    name = "tts"

    def __init__(self, settings: Settings):
        self.kokoro_url = settings.tts_kokoro_url.rstrip("/") if settings.tts_kokoro_url else ""
        self.kokoro_voice = settings.tts_kokoro_voice
        self.piper_enabled = settings.tts_piper_enabled
        self.piper_model = settings.tts_piper_model
        self.speed = settings.tts_speed
        self._piper_available: bool | None = None

    async def initialize(self) -> None:
        if self.piper_enabled and self.piper_model:
            self._piper_available = shutil.which("piper") is not None
            if not self._piper_available:
                logger.warning("Piper TTS enabled but 'piper' binary not found in PATH")
        elif self.piper_enabled:
            self._piper_available = False
            logger.info("Piper TTS enabled but no model configured (tts_piper_model empty)")
        else:
            self._piper_available = False

        backends = []
        if self.kokoro_url:
            backends.append(f"kokoro ({self.kokoro_url})")
        if self._piper_available:
            backends.append("piper (local)")
        if backends:
            logger.info("TTS backends: %s", ", ".join(backends))
        else:
            logger.warning("No TTS backends configured")

    async def synthesize(self, text: str) -> bytes:
        """Generate WAV audio bytes. Tries Kokoro first, then Piper."""
        if not text or not text.strip():
            raise ValueError("Empty text")

        logger.info("[TTS] synthesize() called — %d chars", len(text))

        if self.kokoro_url:
            logger.info("[TTS] Trying Kokoro at %s (voice=%s, speed=%s)...", self.kokoro_url, self.kokoro_voice, self.speed)
            t0 = time.monotonic()
            try:
                result = await self._kokoro_synthesize(text)
                elapsed = (time.monotonic() - t0) * 1000
                logger.info("[TTS] Kokoro SUCCESS — %d bytes in %.0fms (Mac Mini)", len(result), elapsed)
                return result
            except Exception as e:
                elapsed = (time.monotonic() - t0) * 1000
                logger.warning("[TTS] Kokoro FAILED in %.0fms: %s — trying Piper fallback", elapsed, e)

        if self._piper_available:
            logger.info("[TTS] Trying Piper locally (model=%s)...", self.piper_model)
            t0 = time.monotonic()
            try:
                result = await self._piper_synthesize(text)
                elapsed = (time.monotonic() - t0) * 1000
                logger.info("[TTS] Piper SUCCESS — %d bytes in %.0fms (Pi local)", len(result), elapsed)
                return result
            except Exception as e:
                elapsed = (time.monotonic() - t0) * 1000
                logger.warning("[TTS] Piper FAILED in %.0fms: %s", elapsed, e)

        logger.error("[TTS] All backends failed — no TTS available")
        raise TTSUnavailableError("No TTS backend available")

    async def _kokoro_synthesize(self, text: str) -> bytes:
        """Call Kokoro-FastAPI on Mac Mini (OpenAI-compatible endpoint)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.kokoro_url}/v1/audio/speech",
                json={
                    "model": "kokoro",
                    "input": text,
                    "voice": self.kokoro_voice,
                    "speed": self.speed,
                    "response_format": "wav",
                },
            )
            resp.raise_for_status()
            return resp.content

    async def _piper_synthesize(self, text: str) -> bytes:
        """Run Piper locally via subprocess. Returns WAV bytes."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            proc = await asyncio.create_subprocess_exec(
                "piper",
                "--model", self.piper_model,
                "--output_file", tmp_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate(input=text.encode("utf-8"))
            if proc.returncode != 0:
                raise RuntimeError(f"Piper failed (exit {proc.returncode}): {stderr.decode()}")
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def health_check(self) -> dict:
        backends = []
        if self.kokoro_url:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{self.kokoro_url}/v1/audio/voices")
                    if resp.status_code < 500:
                        backends.append("kokoro")
            except Exception:
                pass
        if self._piper_available:
            backends.append("piper")

        healthy = len(backends) > 0
        return {
            "healthy": healthy,
            "details": f"backends: {', '.join(backends)}" if backends else "no backends available",
            "backends": backends,
        }


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    """Wrap raw PCM data in a WAV header."""
    import struct

    data_size = len(pcm)
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,        # file size - 8
        b"WAVE",
        b"fmt ",
        16,                    # chunk size
        1,                     # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,      # bits per sample
        b"data",
        data_size,
    )
    return header + pcm
