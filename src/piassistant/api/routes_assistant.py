from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """Send a message to the assistant."""
    agent = request.app.state.agent
    response = await agent.process(body.message)
    return ChatResponse(response=response)


@router.post("/reset")
async def reset(request: Request):
    """Reset conversation history."""
    request.app.state.agent.reset()
    return {"status": "ok", "message": "Conversation reset"}
