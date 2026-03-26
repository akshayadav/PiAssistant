import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..services.tts import TTSService, TTSUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter()


class SpeakRequest(BaseModel):
    text: str


@router.post("/voice/speak")
async def speak(request: Request, body: SpeakRequest):
    """Convert text to speech. Returns WAV audio."""
    t0 = time.monotonic()
    text_preview = body.text[:80] + ("..." if len(body.text) > 80 else "")
    logger.info("[TTS route] POST /voice/speak — %d chars: %r", len(body.text), text_preview)
    tts: TTSService = request.app.state.registry.get("tts")
    try:
        audio_bytes = await tts.synthesize(body.text)
    except TTSUnavailableError:
        logger.warning("[TTS route] No TTS backend available")
        return Response(status_code=503, content="No TTS backend available")
    except ValueError as e:
        logger.warning("[TTS route] Bad request: %s", e)
        return Response(status_code=400, content=str(e))
    elapsed = (time.monotonic() - t0) * 1000
    logger.info("[TTS route] Returning %d bytes WAV in %.0fms", len(audio_bytes), elapsed)
    return Response(content=audio_bytes, media_type="audio/wav")


@router.get("/voice/config")
async def voice_config(request: Request):
    """Return TTS configuration for the frontend."""
    tts: TTSService = request.app.state.registry.get("tts")
    health = await tts.health_check()
    return {
        "available": health["healthy"],
        "backends": health.get("backends", []),
    }
