from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    image: Optional[str] = None      # Base64-encoded image data
    image_mime: Optional[str] = None  # e.g. "image/jpeg", "image/png"


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """Send a message to the assistant. Optionally include a base64 image for vision analysis."""
    agent = request.app.state.agent

    if body.image:
        response = await agent.process_vision(
            user_message=body.message,
            image_b64=body.image,
            mime_type=body.image_mime or "image/jpeg",
        )
    else:
        response = await agent.process(body.message)

    return ChatResponse(response=response)


@router.post("/reset")
async def reset(request: Request):
    """Reset conversation history."""
    request.app.state.agent.reset()
    return {"status": "ok", "message": "Conversation reset"}
