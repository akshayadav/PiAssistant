# Local LLM Integration Plan

## Problem Statement

PiAssistant used the Anthropic Claude API as its brain. Every chat message — including simple weather checks, timer sets, and grocery list updates — consumed API tokens billed against the Anthropic API payment system (not the Claude Pro subscription). This was unsustainable for a home assistant running 24/7.

## Decision: Local LLM on Mac Mini

### Why Mac Mini, not Pi or Jetson?

| Factor | Pi 5 (8GB) | Jetson Orin Nano (8GB) | Mac Mini M4 (16GB) |
|---|---|---|---|
| RAM for models | ~4GB usable | ~5GB usable | ~10GB usable |
| Best model size | 3-4B Q4 | 7-8B Q4 | 8-12B Q4 (or 35B MoE) |
| Inference speed | ~5 tok/s (CPU) | ~30-40 tok/s (GPU) | ~50-70 tok/s (MLX) |
| Tool use quality | Poor (too small) | Decent | Good |
| Already available | Yes | No (future) | Yes |

**Chosen**: Mac Mini M4 16GB — already on the network, fast enough for real-time assistant responses, large enough RAM for quality tool-use models.

### Architecture

```
User (dashboard/CLI/voice)
    |
Pi 5 (FastAPI /api/chat)
    |
LLMService --> HTTP --> Mac Mini (LM Studio, OpenAI-compatible API)
    |
Tool-use loop (weather, grocery, timers, etc.)
    |
Response back to user
```

The Pi remains the hub/orchestrator. It sends LLM requests to the Mac Mini over the local network. All services (weather, grocery, timers, etc.) still run on the Pi.

### LLMService Dual Backend

`LLMService` now supports two backends, controlled by `LLM_BACKEND` env var:

| Setting | Backend | Use Case |
|---|---|---|
| `LLM_BACKEND=local` | LM Studio on Mac Mini (OpenAI-compatible API) | Default — free, fast |
| `LLM_BACKEND=anthropic` | Claude API (Anthropic SDK) | Premium — best quality, costs money |

Switching is a one-line `.env` change. No code changes needed.

### Unified Response Format

Both backends return the same `LLMResponse` dataclass:
- `LLMResponse.content` — list of `TextBlock` and `ToolUseBlock`
- `LLMResponse.stop_reason` — `"end_turn"` or `"tool_use"`

The Agent doesn't know or care which backend is active.

## Model Selection

### Mac Mini M4 16GB — What Fits

| Model | Params | Active | VRAM | Speed (MLX) | Tool Use |
|---|---|---|---|---|---|
| Qwen 3 4B | 4B | 4B | ~2.5GB | ~80-100 tok/s | Decent |
| Qwen 3 8B | 8B | 8B | ~5GB | ~50-70 tok/s | Good |
| Gemma 3 12B QAT 4bit | 12B | 12B | ~7.5GB | ~25-35 tok/s | Good |
| Qwen3.5-35B-A3B (MoE) | 35B | 3B | ~3-5GB | ~70-90 tok/s | Very good |

### Current Model: Gemma 3 12B (QAT 4-bit, MLX)

**Why**: Already downloaded, confirmed working with tool calling via LM Studio. QAT (quantization-aware training) means better quality than post-hoc quantization.

**Limitation**: Slower than smaller models due to 12B size. ~25-35 tok/s on M4.

### Recommended Upgrade Path

1. **Qwen 3 8B MLX** — best balance of speed and tool-use quality
2. **Qwen3.5-35B-A3B** — if full GGUF/MLX can be downloaded, fastest smart option (only 3B active per token)

### Format: MLX over GGUF

| Factor | GGUF (llama.cpp) | MLX |
|---|---|---|
| Built for | Cross-platform | Apple Silicon specifically |
| Metal optimization | Via translation layer | Native |
| Speed on M4 | ~30-40 tok/s (8B) | ~50-70 tok/s (8B) |
| Memory efficiency | Good | Better (unified memory, zero-copy) |

**Decision**: Use MLX format for all models on Mac Mini. Apple's own ML framework, optimized for M-series unified memory.

## Tool Filtering (Performance Optimization)

### Problem

Sending all 32 tool definitions (~3-4K tokens) every request is slow for a 12B local model. The model spends significant time processing tool schemas before generating a response.

### Solution

Keyword-based tool filtering: scan the user's message and only include relevant tool groups.

### Tool Groups

| Group | Keywords | Tools | Count |
|---|---|---|---|
| weather | weather, temperature, forecast, rain, hot, cold, humid | 2 | get_current_weather, get_weather_forecast |
| news | news, headlines, article, happening, current events | 2 | get_news_headlines, search_news |
| grocery | grocery, shopping, buy, store, price, costco, safeway, list | 10 | grocery_* |
| timers | timer, alarm, countdown, minutes, seconds | 3 | timer_* |
| tasks | task, todo, remind, reminder, schedule, priority, overdue | 6 | task_* |
| notes | note, remember, save, jot | 2 | note_* |
| calendar | calendar, event, meeting, schedule, appointment | 2 | get_calendar_events, add_calendar_event |
| network | network, device, ping, online, offline | 2 | list_network_devices, add_network_device |
| orders | order, amazon, delivery, package, tracking | 2 | get_orders, refresh_orders |
| system | system, cpu, memory, disk, temperature, uptime, status | 1 | get_system_status |
| quote | quote, inspiration, motivation, motivate | 1 | get_daily_quote |

### Filtering Rules

1. Scan user message for keywords (case-insensitive)
2. Include all tool groups that match
3. If no keywords match, include ALL tools (fallback for ambiguous requests)
4. For "daily brief" / "summary" requests, include weather + tasks + grocery + calendar
5. Always include task tools for auto-do evaluation (tasks may trigger other tools)

### Expected Impact

| Scenario | Before | After | Speedup |
|---|---|---|---|
| "What's the weather?" | 32 tools (~3.5K tokens) | 2 tools (~200 tokens) | ~2-3x |
| "Add milk to grocery" | 32 tools | 10 tools (~1K tokens) | ~1.5-2x |
| "Daily brief" | 32 tools | ~20 tools (~2K tokens) | ~1.3x |
| General question (no tools) | 32 tools | 0 tools | ~2-3x |

## Implementation Log

### 2026-03-27: Initial Local LLM Integration
- Added `LLM_BACKEND`, `LMSTUDIO_URL`, `LMSTUDIO_MODEL` config settings
- Refactored `LLMService` for dual backend (Anthropic + OpenAI-compatible)
- Created unified response types: `LLMResponse`, `TextBlock`, `ToolUseBlock`
- Added Anthropic-to-OpenAI tool format converter
- Added message format converter (handles tool_result blocks)
- Verified end-to-end: Pi → Mac Mini (Gemma 3 12B) → tool call → weather data → response
- 93 tests passing
- Deployed to Pi, confirmed working via `/api/chat`

### 2026-03-27: Tool Filtering
- Keyword-based tool group selection
- Reduces tool payload from 32 → 2-10 per request
- Fallback: all tools if no keywords match

## Multi-Model Strategy

LM Studio can load multiple models simultaneously. Current setup:

| Model | Role | RAM | Status |
|---|---|---|---|
| **Qwen 3 8B** (MLX 4-bit) | Chat brain — tool use | ~5GB | Active (`LMSTUDIO_MODEL`) |
| **Gemma 3 12B** (MLX QAT 4-bit) | Future vision (multimodal) | ~7.5GB | Loaded, reserved |

Both loaded uses ~12.5GB of 16GB — leaves ~3.5GB for macOS, acceptable for a headless server.

**Why keep Gemma loaded**: Gemma 3 is multimodal (vision + text). When the AI camera hat is added, the Pi can send images to Gemma for object detection, scene description, etc. without any external API. A future `VisionService` would target `google/gemma-3-12b` directly while the chat brain continues using Qwen.

## Future Considerations

- **Camera + Gemma vision**: Pi captures image → sends to Gemma 3 12B on Mac Mini → "what do you see?" — fully local vision pipeline.
- **Jetson Orin Nano**: When available, can serve as a second local LLM backend. Same `LLMService` abstraction works — just change URL.
- **Model hot-swap**: Could auto-select model based on query type (Qwen for tools, Gemma for vision).
- **Claude API as premium tier**: Keep `LLM_BACKEND=anthropic` option for when highest quality is needed (e.g., complex multi-tool daily briefs).
- **Ollama alternative**: Same OpenAI-compatible API. Could run alongside or instead of LM Studio.

## Connection Details

| Component | Value |
|---|---|
| Mac Mini IP | 10.0.0.232 |
| LM Studio port | 1234 |
| API endpoint | http://10.0.0.232:1234/v1/chat/completions |
| Chat model | qwen3-8b (MLX, 4-bit) |
| Vision model | google/gemma-3-12b (MLX, QAT 4-bit) — reserved for future camera |
| Pi → Mac Mini latency | <1ms (same LAN) |
