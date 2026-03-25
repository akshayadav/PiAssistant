# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PiAssistant** is a smart assistant running on a Raspberry Pi 5 that acts as a **mothership** — it orchestrates Pico W microcontrollers, handles user interaction (CLI, voice, web), and offloads heavy processing to a Mac Mini on the local network. Claude API is the brain, using tool use to route natural language requests to services.

### How PiAssistant Differs from Sibling Projects

| Project | What | Pi ↔ Pico | Brain | Stack |
|---|---|---|---|---|
| **PiAssistant** (this) | General-purpose smart assistant + Pico W hub | WiFi HTTP/MQTT | Claude tool use (agentic) | Python + FastAPI |
| **PiBot** | Desk companion robot with face/arms | Serial (UART) | Claude chat (no tools) | Python + Flask |
| **PicoWeather** | Standalone weather display | N/A (no Pi) | None | MicroPython |

PiAssistant can learn from PiBot's patterns (brain, speech, vision modules) but improves on them: async FastAPI instead of threaded Flask, Claude tool use instead of plain chat, WiFi instead of serial for Pico W communication, and a cache-first data gateway pattern.

## Architecture Decisions

### Decision: Hybrid Architecture (Pi + Mac Mini)

| Factor | A: Pi Standalone | B: Mac Mini Brain | C: Hybrid (chosen) |
|---|---|---|---|
| Local LLM speed | ~5 tok/s (7B, CPU) | Fast (M-series) | Fast (on Mac Mini) |
| Voice STT/TTS | Sluggish | Fast | Fast (offloaded) |
| Hardware control | Direct GPIO | Needs network hop to Pi | Direct on Pi |
| Reliability | Works if Pi is on | Breaks if Mac Mini off | Degrades gracefully |
| Portability | Take Pi anywhere | Tied to network | Pi works alone for basics |
| Future (robot/mobile) | Ready for mobile | Can't wheel Mac Mini | Best of both |

**Why Hybrid**: Pi must be mobile-capable (future wheels/arms/camera), but Mac Mini is too powerful to ignore. Services abstract where processing happens — a `LLMService` doesn't care if it calls Claude API, Ollama on Mac Mini, or Ollama on a local Jetson GPU.

### Decision: Jetson Migration Path

When migrating from Pi 5 to Jetson Orin Nano:

| Factor | Pi 5 | Jetson Orin Nano |
|---|---|---|
| GPU | None | 1024 Ampere CUDA cores |
| Local LLM | ~5 tok/s (CPU) | ~30-40 tok/s (7B) |
| Whisper STT | ~5x realtime | Near-realtime |
| AI/CV | CPU only — very slow | Real-time object detection |
| Mac Mini needed? | Yes, for heavy tasks | Optional — Jetson handles most locally |

The service abstraction makes this a config/deployment change, not a rewrite. Mac Mini becomes optional on Jetson Orin.

### Decision: Pi 5 Setup

| Decision | Choice | Rationale |
|---|---|---|
| OS | Pi OS Lite 64-bit (Bookworm) | ~50 MB idle RAM vs ~350 MB for Desktop; camera/GPIO work the same; display via kiosk browser instead of full DE |
| Display | Cage + Chromium kiosk (not Desktop DE) | ~100-150 MB vs ~350 MB; fullscreen web dashboard serves Pi display, phone, and Mac from same FastAPI server |
| SSH auth | Public key (ed25519) | More secure, no password to type; Imager injects key during flash |
| Remote access | Tailscale (not Raspberry Pi Connect) | Mesh VPN works from anywhere; direct peer-to-peer (faster than relay); covers all devices (Pi, Mac Mini, laptop) without a Raspberry Pi account |
| Python env | venv (not Docker) | Simpler, less RAM overhead, fast iteration; Docker later if needed |
| MQTT broker | Mosquitto | Lightweight, ready for Pico W push |
| Auto-start | systemd service | Standard, reliable, auto-restart on crash |
| Log storage | USB external drive (/mnt/usblog) | Persistent archive beyond SD card, removable for analysis; fstab with nofail so Pi boots without it |

### Key Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Hybrid: Pi as hub, Mac Mini as backend | Pi orchestrates + hardware, Mac Mini does heavy lifting |
| LLM | Claude API only (for now) | Start simple, add local LLM fallback later |
| Stack | Python + FastAPI | Best for Pi/Jetson hardware, async, matches MicroPython on Picos |
| Interfaces | Terminal (full), Voice (common), Web UI | Terminal first; voice + web deferred |
| Data sources | Free APIs (Open-Meteo, NewsAPI) | Open-Meteo needs no key; web scraping added later |
| Pico W comms | HTTP now, MQTT later | Pi caches data, serves Picos — one API fetch serves all |
| Pi role | Mothership — gateway, cache, orchestrator | Minimizes API calls, centralizes data |

## Project Structure

```
PiAssistant/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example              # API keys template (never commit .env)
├── .gitignore
├── .mcp.json                 # MCP server config (committed)
├── data/                     # SQLite DB (git-ignored)
├── deploy/
│   ├── setup.sh              # Pi setup script
│   ├── piassistant.service   # systemd unit
│   ├── mosquitto.conf        # MQTT config
│   └── claude-hooks.json     # Claude Code hooks template for Mac
├── src/
│   └── piassistant/
│       ├── __init__.py
│       ├── main.py           # Entry point: server + CLI
│       ├── config.py         # Settings via pydantic-settings
│       ├── services/
│       │   ├── base.py       # BaseService ABC + ServiceRegistry
│       │   ├── cache.py      # TTL in-memory cache
│       │   ├── llm.py        # Claude API wrapper (Anthropic SDK)
│       │   ├── weather.py    # Open-Meteo (cache-first, no API key)
│       │   ├── news.py       # NewsAPI.org (cache-first)
│       │   ├── storage.py    # SQLite persistence via aiosqlite
│       │   ├── grocery.py    # Grocery lists by store
│       │   ├── timers.py     # In-memory cooking timers (asyncio)
│       │   ├── reminders.py  # Notes (SQLite); reminders unified into tasks
│       │   ├── todo.py       # TaskService: unified tasks + reminders (SQLite, stale nudging)
│       │   ├── quote.py      # Daily inspirational quote (zenquotes.io + SQLite)
│       │   ├── sysmon.py     # System monitor (psutil — CPU/RAM/disk/temp)
│       │   ├── network.py    # Network device ping monitor (SQLite)
│       │   └── calendar.py   # Calendar events (Google + iCloud CalDAV)
│       ├── brain/
│       │   ├── agent.py      # Tool-use loop: user msg → Claude → tools → response
│       │   └── tools.py      # Tool definitions for Claude (30 tools)
│       ├── api/
│       │   ├── app.py        # FastAPI app factory
│       │   ├── middleware.py        # API key auth middleware (Bearer token on write endpoints)
│       │   ├── routes_assistant.py  # /api/chat — human interaction
│       │   ├── routes_pico.py       # /api/pico/* — compact JSON for Pico Ws
│       │   ├── routes_health.py     # /api/health, /api/config — diagnostics + frontend config
│       │   ├── routes_kiosk.py      # /api/grocery, /api/timers, etc. — widget data
│       │   ├── routes_hooks.py      # /api/hooks/* — Claude Code session monitor
│       │   └── routes_terminal.py   # /api/terminal/* — WebSocket SSH bridge to Mac Mini
│       ├── static/
│       │   ├── index.html           # Web dashboard with widget grid
│       │   ├── css/dashboard.css    # Dashboard styles
│       │   └── js/dashboard.js      # Widget JS (polling, interactions)
│       └── cli/
│           └── repl.py       # Interactive terminal REPL
└── tests/
```

## Core Design Patterns

### Service Abstraction

Every capability is a `BaseService` with `async initialize()`, `async health_check()`, and a `name` property. Services are registered explicitly in `main.py` via `ServiceRegistry` (dict-based, no autodiscovery). The registry is injected into FastAPI app and brain agent.

Adding a new capability = add service + add Claude tool definition + add dispatch case.

### Brain: Claude Tool Use Loop

Unlike PiBot (plain chat), PiAssistant uses Claude's **tool use** for agentic routing:
1. User says something natural → send to Claude with tool definitions
2. If Claude returns `tool_use` → execute tools via service registry
3. Send tool results back → Claude synthesizes natural language response
4. Repeat until Claude returns `end_turn`

### Cache-First Data Gateway (Mothership Pattern)

WeatherService and NewsService: check in-memory TTL cache → if miss, fetch from external API, cache, return. Multiple Pico Ws requesting weather get served from one cached API call.

### Pico W Endpoints

`/api/pico/*` returns **compact JSON** (short keys, minimal payload) because Pico W has ~264KB RAM. Example: `{"temp": 72, "desc": "Cloudy", "hum": 45}`.

### CLI Architecture

The REPL talks to FastAPI over HTTP, not directly to the brain. This means CLI can run from any machine on the network, and the same brain logic serves CLI, Pico W, and future web UI.

## Progress & Roadmap

### Completed
- [x] Project groundwork: git, CLAUDE.md, memory files, MCP servers, scaffold
- [x] Service layer: BaseService, ServiceRegistry, CacheService, LLMService, WeatherService, NewsService
- [x] Brain: Claude tool-use loop with 4 tools (weather, forecast, headlines, news search)
- [x] FastAPI server: /api/chat, /api/pico/*, /api/health
- [x] CLI REPL
- [x] Switched weather from OpenWeatherMap to Open-Meteo (no API key, better data)
- [x] GitHub repo created
- [x] Homebrew + gh CLI installed on dev Mac
- [x] Pi 5 deployment: systemd service, Mosquitto config, setup script, CLI remote URL support
- [x] Connect PicoWeather to mothership: `/api/pico/weather?units=metric`, PicoWeather tries Pi first with Open-Meteo fallback
- [x] Web dashboard: single-page chat UI at `/` with weather bar, dark theme, responsive
- [x] Pi 5 deployed: repo cloned, venv, systemd service running, all endpoints verified
- [x] Kiosk display: Cage + Chromium fullscreen dashboard on HDMI
- [x] Kiosk features — SQLite persistence, grocery lists (6 default stores), cooking timers, reminders, notes, to-do lists
- [x] Claude Code session monitor — HTTP hooks receiver, in-memory session tracking, dashboard widget
- [x] Dashboard overhaul — CSS Grid widget layout (weather, sessions, timers, reminders, grocery, notes, todos, chat)
- [x] 20 initial Claude tools (weather 2, news 2, grocery 4, timers 3, reminders 2, notes 2, todos 3) — later unified into 31 tools
- [x] Enhanced system prompt with all capabilities + free features (conversions, recipes, math)
- [x] 31 initial tests passing
- [x] Claude Code hooks configured on Mac — `~/.claude/settings.json` pushes 6 event types to Pi via HTTP hooks with X-Machine header
- [x] Walkthrough doc: `docs/claude-session-monitor.md`
- [x] News dashboard widget — 4 configurable feeds (Global, India, Indore, Santa Clara), 6-hour cache TTL, add/remove from UI
- [x] Walkthrough doc: `docs/news-dashboard-widget.md`
- [x] Read headlines aloud — browser TTS (Web Speech API), ▶ Read / ■ Stop button in news widget header
- [x] Daily Quote widget — zenquotes.io API, 24h cache, SQLite persistence, fallback quotes
- [x] Pi System Monitor widget — psutil for CPU/RAM/disk/temp/uptime, 10s cache, color-coded progress bars
- [x] Network Devices widget — ping-based monitoring, background 60s sweep, add/remove devices, SQLite persistence
- [x] Calendar widget — Google Calendar OAuth2 + iCloud CalDAV, merged timeline view, color-coded sources
- [x] 31 Claude tools (weather 2, news 2, calendar 2, network 2, sysmon 1, quote 1, orders 2, grocery 4, timers 3, tasks 6, notes 2, system prompt updated)
- [x] 60 tests passing
- [x] Configurable display name — `assistant_name` setting (default "Bunty"), served via `/api/config`, dashboard fetches on load; change in `.env` without touching code
- [x] LinkedIn post draft — `docs/linkedin-sessions-post.md` (Claude Code session monitor)
- [x] Remote access — Cloudflare Tunnel (`bunty.akshayadav.com`), API key auth middleware (dormant), CLI auth, hooks env vars, 67 tests passing
- [x] Web Terminal — xterm.js + WebSocket SSH bridge to Mac Mini, run Claude Code from dashboard, fullscreen toggle, "Start Claude" button, 67 tests passing
- [x] Unified Task Management — merged todos + reminders into single `tasks` table, priority levels, due dates, background stale-task nudging (5-min asyncio loop), AI scheduling suggestions via `task_suggest` tool, dashboard visual + audio nudges, 86 tests passing

### Up Next (in priority order)
1. **USB log archiving** — external USB drive at /mnt/usblog, `log_archive_path` config setting, fstab with nofail
2. **Voice (STT/TTS)** — hands-free interaction, offloaded to Mac Mini
3. **MQTT push** — Pi pushes weather updates to Pico Ws instead of polling

### Future
- Local LLM fallback (Ollama on Mac Mini)
- AI camera hat integration
- Motors/servos for arms/wheels
- Jetson Nano/Orin migration
- Web scraping as alternative data source

## Build & Run Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then edit with real API keys

# Run server
python -m piassistant

# Run CLI (separate terminal, talks to server)
python -m piassistant cli

# Run CLI pointing at remote Pi
python -m piassistant cli http://piassistant-mothership.local:8000
# Or: PIASSISTANT_URL=http://piassistant-mothership.local:8000 python -m piassistant cli

# Run tests
pytest tests/

# Test endpoints
curl http://localhost:8000/api/health
curl http://localhost:8000/api/pico/weather
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in New York?"}'
```

## Pi 5 Deployment

**OS**: Raspberry Pi OS Lite 64-bit (Bookworm) — lowest RAM overhead, best Pi 5 hardware support.

**Connection details**:
- Hostname: `PiAssistant-Mothership` (mDNS: `piassistant-mothership.local`)
- User: `akshay`
- SSH: `ssh akshay@piassistant-mothership.local`
- Kernel: Linux 6.12 aarch64

See [deploy/README.md](deploy/README.md) for full instructions. Key files:

| File | Purpose |
|---|---|
| `deploy/setup.sh` | One-script Pi setup (apt, venv, systemd install) |
| `deploy/piassistant.service` | systemd unit file |
| `deploy/mosquitto.conf` | MQTT broker config for Pico W access |
| `~/.bash_profile` (on Pi) | Kiosk auto-launch: Cage + Chromium on tty1 |

```bash
# Quick deploy (on Pi)
git clone <repo-url> ~/PiAssistant && cd ~/PiAssistant
bash deploy/setup.sh
nano .env  # add API keys
sudo systemctl start piassistant

# Manage
sudo systemctl status piassistant
journalctl -u piassistant -f
```

**Tailscale** provides secure remote access from anywhere: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`

### Remote Access (Cloudflare Tunnel)

PiAssistant is publicly accessible at **https://bunty.akshayadav.com** via Cloudflare Tunnel.

| Component | Detail |
|---|---|
| Domain | `akshayadav.com` (Namecheap, DNS via Cloudflare free plan) |
| Tunnel | `cloudflared` on Pi, systemd service, auto-starts on boot |
| HTTPS | Automatic via Cloudflare |
| Auth | Optional API key middleware (`api/middleware.py`), currently disabled |

**How it works**: `cloudflared` on the Pi creates an outbound connection to Cloudflare's edge. No ports opened on the router. Cloudflare routes `bunty.akshayadav.com` through the tunnel to `localhost:8000`.

**Manage tunnel**:
```bash
sudo systemctl status cloudflared    # check tunnel
sudo systemctl restart cloudflared   # restart tunnel
```

**Optional API key auth**: Set `API_KEY=<secret>` in `.env` to protect POST/PUT/DELETE/PATCH endpoints. GET endpoints always pass through. CLI supports `PIASSISTANT_API_KEY` env var. Currently not enabled.

**Claude Code hooks**: Set `PIASSISTANT_URL=https://bunty.akshayadav.com` env var — hooks in `deploy/claude-hooks.json` use it automatically (falls back to mDNS if unset).

### Web Terminal (SSH Bridge)

The dashboard includes an xterm.js terminal that bridges to the Mac Mini via SSH. This lets you run Claude Code (or any command) from the browser.

**Architecture**: `Browser (xterm.js) ←WebSocket→ Pi (FastAPI /api/terminal/ws) ←SSH (asyncssh)→ Mac Mini shell`

**SSH key setup** (on Pi):
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_macmini -N ""
ssh-copy-id -i ~/.ssh/id_ed25519_macmini.pub akshay@<mac-mini-host>
ssh -i ~/.ssh/id_ed25519_macmini akshay@<mac-mini-host> echo ok
```

**Then in `.env`**:
```
TERMINAL_SSH_HOST=<mac-mini-host>
TERMINAL_SSH_USER=akshay
TERMINAL_SSH_KEY=/home/akshay/.ssh/id_ed25519_macmini
```

Terminal section is hidden when not configured. WebSocket auth uses `?token=` query param when `API_KEY` is set.

## MCP Servers

| Server | Purpose | Phase |
|---|---|---|
| GitHub | Repo management, issues, PRs | Now |
| Fetch | Test weather/news API calls during dev | Now |
| SSH | Deploy and manage Pi remotely from Mac | When deploying to Pi |
| FastAPI-MCP | Expose PiAssistant endpoints as MCP tools | Future |
| MQTT bridge | Pico W push notifications | Future |

## Deferred (But Architected For)

| Feature | How architecture accommodates it |
|---|---|
| Voice (STT/TTS) | Add `STTService`/`TTSService` → brain receives text from STT instead of HTTP |
| Web UI | FastAPI serves JSON → add frontend that calls `/api/chat` |
| MQTT push | Hook into cache updates → publish to MQTT topics on refresh |
| Mac Mini offload | Change service backends (LLM, STT) to call Mac Mini HTTP endpoints |
| Local LLM fallback | New `LocalLLMService` with same interface, swap via config |
| Jetson migration | Service abstraction = same code, different deployment |
| Hardware (camera, servos) | New services + new Claude tool definitions, same pattern |
