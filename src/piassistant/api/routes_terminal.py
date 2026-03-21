import asyncio
import json

import asyncssh
from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.get("/terminal/status")
async def terminal_status(request: Request):
    """Check if terminal SSH bridge is configured and password-protected."""
    settings = request.app.state.settings
    configured = bool(
        settings.terminal_ssh_host
        and settings.terminal_ssh_user
        and settings.terminal_password
    )
    return {
        "configured": configured,
        "host": settings.terminal_ssh_host if configured else "",
    }


@router.websocket("/terminal/ws")
async def terminal_ws(ws: WebSocket, token: str = Query(default="")):
    settings = ws.app.state.settings

    # Check if terminal is configured
    if not settings.terminal_ssh_host or not settings.terminal_ssh_user or not settings.terminal_password:
        await ws.accept()
        await ws.send_text("\r\nTerminal not configured.\r\n")
        await ws.close()
        return

    # Password check (required)
    if token != settings.terminal_password:
        await ws.accept()
        await ws.send_text("\r\nIncorrect password.\r\n")
        await ws.close()
        return

    await ws.accept()
    await ws.send_text(f"Connecting to {settings.terminal_ssh_host}...\r\n")

    try:
        connect_kwargs = {
            "host": settings.terminal_ssh_host,
            "port": settings.terminal_ssh_port,
            "username": settings.terminal_ssh_user,
            "known_hosts": None,
        }
        if settings.terminal_ssh_key:
            connect_kwargs["client_keys"] = [settings.terminal_ssh_key]

        conn = await asyncssh.connect(**connect_kwargs)
    except Exception as e:
        await ws.send_text(f"\r\nSSH connection failed: {e}\r\n")
        await ws.close()
        return

    try:
        proc = await conn.create_process(
            term_type="xterm-256color",
            term_size=(120, 30),
        )

        async def ws_to_ssh():
            """Read from WebSocket, forward to SSH stdin."""
            try:
                while True:
                    data = await ws.receive_text()
                    # Check for resize messages
                    if data.startswith('{"type":"resize"'):
                        try:
                            msg = json.loads(data)
                            if msg.get("type") == "resize":
                                proc.change_terminal_size(
                                    msg.get("cols", 120),
                                    msg.get("rows", 30),
                                )
                                continue
                        except json.JSONDecodeError:
                            pass
                    proc.stdin.write(data)
            except (WebSocketDisconnect, Exception):
                pass

        async def ssh_to_ws():
            """Read from SSH stdout, forward to WebSocket."""
            try:
                while True:
                    data = await proc.stdout.read(4096)
                    if not data:
                        break
                    await ws.send_text(data)
            except Exception:
                pass

        ws_task = asyncio.create_task(ws_to_ssh())
        ssh_task = asyncio.create_task(ssh_to_ws())

        # Wait for either side to finish
        done, pending = await asyncio.wait(
            [ws_task, ssh_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        proc.close()
        conn.close()
        try:
            await ws.close()
        except Exception:
            pass
