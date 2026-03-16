# PiAssistant

Smart assistant running on Raspberry Pi 5 with Claude AI as the brain. Acts as a **mothership** for Pico W microcontrollers — caches external data and serves it to Picos over WiFi, minimizing API calls.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Cloud APIs                        │
│         (Claude, OpenWeatherMap, NewsAPI)             │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────┐
│  Mac Mini (backend)   │                              │
│  ┌─────────────────┐  │  (heavy processing:          │
│  │ Local LLM       │  │   LLM fallback, STT, TTS)   │
│  │ STT/TTS         │  │                              │
│  └─────────────────┘  │                              │
└───────────────────────┼─────────────────────────────┘
                        │ local network
┌───────────────────────┼─────────────────────────────┐
│  Raspberry Pi 5       │  (mothership)                │
│  ┌─────────────────────────────────────────────┐    │
│  │  FastAPI Server                              │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │    │
│  │  │ Brain    │ │ Services │ │ Cache Layer  │ │    │
│  │  │ (Claude  │ │ Weather  │ │ (TTL, serves │ │    │
│  │  │ tool use)│ │ News     │ │  all Picos)  │ │    │
│  │  └──────────┘ └──────────┘ └──────────────┘ │    │
│  └──────────────────┬──────────────────────────┘    │
│              ┌──────┴───────┐                        │
│              │   REST API   │                        │
│              └──────┬───────┘                        │
└─────────────────────┼───────────────────────────────┘
          ┌───────────┼───────────┐
          │           │           │
     ┌────┴────┐ ┌────┴────┐ ┌───┴─────┐
     │ Pico W  │ │ Pico W  │ │ Pico W  │
     │ Weather │ │ Display │ │ Sensor  │
     │ Station │ │ Panel   │ │ Hub     │
     └─────────┘ └─────────┘ └─────────┘
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in API keys

# Run server
python -m piassistant.main

# Chat via CLI (separate terminal)
python -m piassistant.main cli

# Test Pico W endpoint
curl http://localhost:8000/api/pico/weather
```

## Related Projects

- **[PiBot](../PiBot)** — Desk companion robot (Pi + Pico W, servos, face tracking, speech)
- **[PicoWeather](../PicoWeather)** — Standalone weather display on Pico W
