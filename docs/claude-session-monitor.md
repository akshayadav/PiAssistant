# Real-Time Claude Code Session Monitor on a Raspberry Pi Kiosk

## The Idea

I have a Raspberry Pi 5 running as a smart home hub (PiAssistant) with a fullscreen kiosk dashboard on an HDMI display. I wanted a way to **see all my Claude Code sessions at a glance** — which projects are active, whether Claude is thinking, running a tool, or waiting for input — all displayed on the Pi's always-on screen.

The result: a live session monitor widget that updates every 2 seconds, showing real-time status badges for every Claude Code session across all my machines.

## How It Works

The architecture is simple:

```
Mac (Claude Code)  ──HTTP POST──>  Raspberry Pi 5 (PiAssistant)
                                        │
                                   FastAPI endpoint
                                   stores sessions
                                   in memory
                                        │
                                   Kiosk dashboard
                                   polls every 2s
                                   shows live status
```

**Claude Code has a built-in hooks system.** You configure it in `~/.claude/settings.json` and it will POST JSON to a URL whenever key events happen — session starts, user prompts, tool use, session ends.

**The Pi receives these events** at a single endpoint (`POST /api/hooks/event`), updates an in-memory session store, and the dashboard widget polls `GET /api/hooks/sessions` every 2 seconds to render live cards.

## Step-by-Step Setup

### 1. The Pi-Side: Hook Receiver (FastAPI)

The hook receiver is a single file — `routes_hooks.py`. It does three things:
- Receives POST events from Claude Code
- Maintains an in-memory dict of active sessions
- Auto-expires sessions after 30 minutes of inactivity

```python
# In-memory session store
_sessions: dict[str, dict] = {}

@router.post("/event")
async def hook_event(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    event = body.get("hook_event_name", "")
    cwd = body.get("cwd", "")
    machine = request.headers.get("X-Machine", "")

    # Update session status based on event type
    if event == "SessionStart":
        session["status"] = "active"
    elif event == "UserPromptSubmit":
        session["status"] = "thinking"
    elif event == "PreToolUse":
        tool_name = body.get("tool_name", "tool")
        session["status"] = f"running: {tool_name}"
    elif event == "Stop":
        session["status"] = "waiting for input"
    elif event == "Notification":
        session["status"] = "needs attention"
    elif event == "SessionEnd":
        _sessions.pop(session_id, None)
```

The project name is derived from the `cwd` path — just the last directory component (e.g., `/Users/akshay/Projects/PiAssistant` → "PiAssistant").

### 2. The Dashboard Widget (Vanilla JS)

The sessions widget on the kiosk dashboard polls the Pi's API every 2 seconds and renders session cards with color-coded status badges:

| Status | Badge Color | When |
|---|---|---|
| thinking | Yellow | User submitted a prompt, Claude is processing |
| running: Bash | Blue | Claude is executing a tool (shows which tool) |
| waiting for input | Green | Claude finished, waiting for next prompt |
| needs attention | Red (pulsing) | Claude sent a notification |
| active | Gray | Session just started |

Each card shows:
- **Project name** (from working directory)
- **Status badge** (color-coded)
- **Machine name** (which computer the session is on)
- **Session duration** (how long it's been running)
- **Idle time** (if idle > 60 seconds)

```javascript
function statusBadge(status) {
  let cls = "badge-active";
  if (status === "thinking") cls = "badge-thinking";
  else if (status.startsWith("running")) cls = "badge-running";
  else if (status === "waiting for input") cls = "badge-waiting";
  else if (status === "needs attention") cls = "badge-attention";
  return `<span class="badge ${cls}">${status}</span>`;
}
```

### 3. The Mac-Side: Claude Code Hook Configuration

This is the key step — telling Claude Code to push events to the Pi. Add a `hooks` section to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://piassistant-mothership.local:8000/api/hooks/event -H 'Content-Type: application/json' -H 'X-Machine: MacMini' -d \"$(cat /dev/stdin)\" --connect-timeout 3 > /dev/null 2>&1 || true"
          }
        ]
      }
    ]
  }
}
```

**Key details:**
- `"type": "command"` — hooks run a shell command; we use `curl` to POST the event JSON to the Pi
- Claude Code pipes the hook payload JSON to stdin — `$(cat /dev/stdin)` captures it and passes it as the `-d` body
- `--connect-timeout 3` + `|| true` — never blocks Claude Code if the Pi is unreachable
- `X-Machine: MacMini` header — so the dashboard knows which computer the session is on
- The URL uses mDNS (`piassistant-mothership.local`) — works on any LAN without hardcoding IPs
- `"matcher": ""` — empty string matches all events (required field in Claude Code hooks config)

### 4. The Hook Event Flow

Here's what happens during a typical Claude Code interaction:

```
1. User opens Claude Code on Mac
   → SessionStart hook fires
   → Pi creates session card: "PiAssistant" [active]

2. User types "Add milk to the Whole Foods list"
   → UserPromptSubmit hook fires
   → Dashboard updates: "PiAssistant" [thinking] (yellow)

3. Claude decides to use the grocery_add tool
   → PreToolUse hook fires with tool_name="Bash"
   → Dashboard updates: "PiAssistant" [running: Bash] (blue)

4. Claude finishes responding
   → Stop hook fires
   → Dashboard updates: "PiAssistant" [waiting for input] (green)

5. User closes Claude Code
   → SessionEnd hook fires
   → Session card removed from dashboard
```

### 5. Testing with curl

You can test the whole flow without Claude Code by sending events manually:

```bash
# Simulate a session starting
curl -X POST http://piassistant-mothership.local:8000/api/hooks/event \
  -H "Content-Type: application/json" \
  -H "X-Machine: MacMini" \
  -d '{"session_id":"test123","hook_event_name":"SessionStart","cwd":"/Users/akshay/Projects/MyProject"}'

# Check sessions
curl http://piassistant-mothership.local:8000/api/hooks/sessions

# Simulate thinking
curl -X POST http://piassistant-mothership.local:8000/api/hooks/event \
  -H "Content-Type: application/json" \
  -H "X-Machine: MacMini" \
  -d '{"session_id":"test123","hook_event_name":"UserPromptSubmit","cwd":"/Users/akshay/Projects/MyProject"}'

# Simulate tool use
curl -X POST http://piassistant-mothership.local:8000/api/hooks/event \
  -H "Content-Type: application/json" \
  -H "X-Machine: MacMini" \
  -d '{"session_id":"test123","hook_event_name":"PreToolUse","cwd":"/Users/akshay/Projects/MyProject","tool_name":"Bash"}'

# Simulate session end
curl -X POST http://piassistant-mothership.local:8000/api/hooks/event \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test123","hook_event_name":"SessionEnd"}'
```

## Architecture Decisions

| Decision | Choice | Why |
|---|---|---|
| Storage | In-memory dict | Sessions are ephemeral — no need for a database. If the Pi reboots, sessions are gone (which is correct — they're stale anyway) |
| Transport | HTTP hooks (not polling) | Claude Code pushes events in real-time. No polling from Pi to Mac needed |
| Machine ID | Custom `X-Machine` header | Simple, no extra infra. Each machine sets its own name in the hooks config |
| Session expiry | 30 minutes idle | Auto-cleanup for sessions that didn't send a clean SessionEnd |
| Dashboard polling | Every 2 seconds | Fast enough to feel real-time, light enough for a Pi |
| Single endpoint | One `/event` URL for all events | Simpler config — every hook type sends to the same URL, server routes by `hook_event_name` |

## What's on the Dashboard

The session monitor is one widget in a larger kiosk dashboard that also shows:
- Weather (from Open-Meteo API)
- Grocery lists (by store, with checkboxes)
- Cooking timers (live countdown)
- Reminders & notes
- To-do list
- Chat interface (talk to Claude via the Pi)

All managed through natural language — "Add milk to the Whole Foods list" or "Set a pizza timer for 12 minutes" — powered by Claude's tool use.

## Tech Stack

- **Raspberry Pi 5** — Pi OS Lite 64-bit, Cage + Chromium kiosk
- **PiAssistant** — Python + FastAPI, Claude API (tool use), SQLite, asyncio
- **Claude Code** — HTTP hooks (built-in feature)
- **Dashboard** — Vanilla HTML/CSS/JS, CSS Grid, no build step
- **Network** — mDNS (`.local`), Tailscale for remote access

## The Meta Moment

The best part? **This very session — where Claude Code helped me build and configure this feature — showed up on the Pi's dashboard as it was being built.** The session monitor was monitoring itself being created.
