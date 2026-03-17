from __future__ import annotations

import time
from pathlib import PurePosixPath

from fastapi import APIRouter, Request

router = APIRouter()

# In-memory session store: {session_id: session_dict}
_sessions: dict[str, dict] = {}

# Auto-expire sessions idle > 30 minutes
SESSION_TIMEOUT = 1800


def _project_name(cwd: str) -> str:
    """Extract project name from cwd path."""
    if not cwd:
        return "unknown"
    return PurePosixPath(cwd).name


def _clean_expired():
    """Remove sessions idle for > SESSION_TIMEOUT."""
    cutoff = time.time() - SESSION_TIMEOUT
    expired = [sid for sid, s in _sessions.items() if s["last_activity"] < cutoff]
    for sid in expired:
        del _sessions[sid]


@router.post("/event")
async def hook_event(request: Request):
    """Receive Claude Code hook events and update session state."""
    body = await request.json()

    session_id = body.get("session_id", "")
    event = body.get("hook_event_name", "")
    cwd = body.get("cwd", "")
    machine = request.headers.get("X-Machine", "")

    if not session_id:
        return {"status": "ignored", "reason": "no session_id"}

    _clean_expired()

    now = time.time()

    if event == "SessionEnd":
        _sessions.pop(session_id, None)
        return {"status": "ok", "action": "removed"}

    # Get or create session
    session = _sessions.get(session_id)
    if session is None:
        session = {
            "session_id": session_id,
            "project": _project_name(cwd),
            "cwd": cwd,
            "machine": machine,
            "status": "active",
            "current_tool": "",
            "started_at": now,
            "last_activity": now,
        }
        _sessions[session_id] = session

    session["last_activity"] = now
    if cwd:
        session["cwd"] = cwd
        session["project"] = _project_name(cwd)
    if machine:
        session["machine"] = machine

    # Update status based on event
    if event == "SessionStart":
        session["status"] = "active"
    elif event == "UserPromptSubmit":
        session["status"] = "thinking"
    elif event == "PreToolUse":
        tool_name = body.get("tool_name", "tool")
        session["status"] = f"running: {tool_name}"
        session["current_tool"] = tool_name
    elif event == "Stop":
        session["status"] = "waiting for input"
        session["current_tool"] = ""
    elif event == "Notification":
        session["status"] = "needs attention"

    return {"status": "ok"}


@router.get("/sessions")
async def get_sessions():
    """Return all active sessions for the dashboard."""
    _clean_expired()
    now = time.time()
    result = []
    for s in _sessions.values():
        result.append({
            "session_id": s["session_id"],
            "project": s["project"],
            "machine": s["machine"],
            "status": s["status"],
            "current_tool": s["current_tool"],
            "duration": round(now - s["started_at"]),
            "idle": round(now - s["last_activity"]),
        })
    return result
