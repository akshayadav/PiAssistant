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
│       │   └── news.py       # NewsAPI.org (cache-first)
│       ├── brain/
│       │   ├── agent.py      # Tool-use loop: user msg → Claude → tools → response
│       │   └── tools.py      # Tool definitions for Claude
│       ├── api/
│       │   ├── app.py        # FastAPI app factory
│       │   ├── routes_assistant.py  # /api/chat — human interaction
│       │   ├── routes_pico.py       # /api/pico/* — compact JSON for Pico Ws
│       │   └── routes_health.py     # /api/health — diagnostics
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
- [x] 18 tests passing
- [x] GitHub repo created
- [x] Homebrew + gh CLI installed on dev Mac

### Up Next (in priority order)
1. **Deploy to Pi 5** — clone repo, install deps, run as systemd service
2. **Connect PicoWeather** — point it at Pi instead of Open-Meteo directly (proves mothership pattern)
3. **Web dashboard** — simple HTML chat page accessible from any device on network
4. **Voice (STT/TTS)** — hands-free interaction, offloaded to Mac Mini
5. **MQTT push** — Pi pushes weather updates to Pico Ws instead of polling

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

# Run tests
pytest tests/

# Test endpoints
curl http://localhost:8000/api/health
curl http://localhost:8000/api/pico/weather
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in New York?"}'
```

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
