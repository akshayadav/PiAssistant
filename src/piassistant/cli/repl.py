import asyncio
import json
import sys

import httpx


async def repl(base_url: str = "http://localhost:8000"):
    """Interactive REPL that talks to the running FastAPI server."""
    client = httpx.AsyncClient(base_url=base_url, timeout=30)

    print("PiAssistant CLI")
    print("Commands: 'quit', 'health', 'reset'")
    print("-" * 40)

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("\nyou> ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break

        if user_input.lower() == "health":
            try:
                r = await client.get("/api/health")
                print(json.dumps(r.json(), indent=2))
            except httpx.ConnectError:
                print("Error: Cannot connect to server. Is it running?")
            continue

        if user_input.lower() == "reset":
            try:
                r = await client.post("/api/reset")
                print(r.json()["message"])
            except httpx.ConnectError:
                print("Error: Cannot connect to server. Is it running?")
            continue

        try:
            r = await client.post("/api/chat", json={"message": user_input})
            data = r.json()
            print(f"\nassistant> {data['response']}")
        except httpx.ConnectError:
            print("Error: Cannot connect to server. Is it running?")
        except Exception as e:
            print(f"Error: {e}")

    await client.aclose()
