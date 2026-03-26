from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..services.tts import TTSService, TTSUnavailableError

router = APIRouter()


class SpeakRequest(BaseModel):
    text: str


@router.post("/voice/speak")
async def speak(request: Request, body: SpeakRequest):
    """Convert text to speech. Returns WAV audio."""
    tts: TTSService = request.app.state.registry.get("tts")
    try:
        audio_bytes = await tts.synthesize(body.text)
    except TTSUnavailableError:
        return Response(status_code=503, content="No TTS backend available")
    except ValueError as e:
        return Response(status_code=400, content=str(e))
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
