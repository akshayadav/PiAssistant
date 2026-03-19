# LinkedIn Post: Building a Real-Time Claude Code Session Monitor

---

I built a real-time session monitor that shows all my Claude Code sessions on a Raspberry Pi kiosk dashboard — and Claude Code helped me build it. I run Claude Code across multiple machines (Mac Mini, laptop, remote via Tailscale), and I wanted a single always-on screen showing what every session is doing. My Pi 5 already runs a kiosk dashboard (PiAssistant) with weather, calendar, grocery lists, timers, and system health — so I added a session monitor widget to it. The workflow that made this possible: a detailed CLAUDE.md file gives Claude Code full project context every session (architecture, patterns, structure), plan mode designed the feature before writing code (in-memory storage, HTTP push via hooks, single endpoint for all event types), and then Claude Code wrote the implementation — a 120-line FastAPI receiver, dashboard JS with color-coded status badges, hooks config template, walkthrough docs, and tests — all following the project's existing conventions.

[IMAGE: Pi kiosk dashboard showing the session monitor widget with color-coded status badges — yellow "thinking", blue "running: Bash", green "waiting for input" — alongside weather, calendar, and grocery widgets]

Here's how it works: Claude Code has a built-in hooks system — you configure `~/.claude/settings.json` with 6 event types (SessionStart, UserPromptSubmit, PreToolUse, Stop, Notification, SessionEnd), and each fires a `curl` POST to the Pi with the event JSON and an `X-Machine` header identifying the source machine. A single FastAPI endpoint on the Pi receives all events, routes by event name, and updates an in-memory session store. The dashboard widget polls every 2 seconds and renders live session cards with color-coded badges: yellow (thinking), blue (running a tool — shows which one), green (waiting for input), red pulsing (needs attention), gray (idle). Sessions auto-expire — idle after 5 minutes, removed after 24 hours. No database needed. Key design choices: mDNS hostname so it works on any LAN without hardcoded IPs, `--connect-timeout 3 || true` so a downed Pi never blocks your coding flow, and each machine self-identifies via a simple header.

[IMAGE: Architecture diagram showing Mac (Claude Code) pushing events via HTTP POST to Raspberry Pi 5 (FastAPI endpoint + in-memory store), with the kiosk dashboard polling the store every 2 seconds]

At a glance on a wall-mounted screen, I can see which projects have active sessions, whether Claude is thinking or waiting, which machine it's on, and how long it's been running. "Is Claude stuck?" — glance at the screen. It scales naturally: add the hooks config to any new machine and its sessions appear automatically. And the best part — while building this feature, the session I was using appeared on the Pi dashboard in real-time. I watched the badge cycle from "thinking" to "running: Write" to "waiting for input" as Claude Code wrote the very code rendering those badges. Claude Code was being monitored by the system it was helping create.

*Built with Claude Code, FastAPI, and a Raspberry Pi 5. Full walkthrough and code on GitHub.*

#ClaudeCode #RaspberryPi #AI #FastAPI #DeveloperTools #BuildInPublic
