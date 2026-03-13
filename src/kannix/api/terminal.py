"""WebSocket terminal proxy: bridges xterm.js to tmux via pty."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import struct
import termios
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from kannix.deps import AppDeps
    from kannix.tmux import TmuxManager

logger = logging.getLogger(__name__)

# Read buffer size
BUF_SIZE = 4096


def create_terminal_router(deps: AppDeps, tmux: TmuxManager) -> APIRouter:
    """Create WebSocket terminal router."""
    router = APIRouter()

    @router.websocket("/ws/terminal/{ticket_id}")
    async def terminal_ws(websocket: WebSocket, ticket_id: str) -> None:
        """WebSocket endpoint for terminal access."""
        # Auth: token from query param
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return
        user = deps.auth_manager.validate_token(token)
        if user is None:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Check ticket exists
        state = deps.state_manager.load()
        if ticket_id not in state.tickets:
            await websocket.close(code=4004, reason="Ticket not found")
            return

        # Ensure tmux session exists with env vars for kannix-ctl
        host = deps.config.server.host
        if host == "0.0.0.0":
            host = "127.0.0.1"
        kannix_env = {
            "KANNIX_URL": f"http://{host}:{deps.config.server.port}",
            "KANNIX_TOKEN": token,
            "KANNIX_TICKET_ID": ticket_id,
        }

        # Add worktree paths for assigned repos
        ticket_state = state.tickets[ticket_id]
        if deps.git_manager:
            for repo_id in ticket_state.repos:
                wt_path = deps.git_manager.get_worktree_path(repo_id, ticket_id)
                repo = deps.git_manager.get_repo(repo_id)
                if wt_path and repo:
                    safe_name = repo.name.upper().replace("-", "_")
                    kannix_env[f"KANNIX_WORKTREE_{safe_name}"] = str(wt_path)

        await websocket.accept()

        # Start in the ticket's workspace directory (always exists)
        start_cwd: str | None = None
        if deps.config.worktree_dir:
            from pathlib import Path

            from kannix.git import ticket_dir_name

            dirname = ticket_dir_name(ticket_id, ticket_state.title)
            ticket_workspace = Path(deps.config.worktree_dir) / dirname
            ticket_workspace.mkdir(parents=True, exist_ok=True)
            start_cwd = str(ticket_workspace)

        try:
            tmux.create_session(ticket_id, env=kannix_env, cwd=start_cwd)
        except Exception:
            logger.exception("Failed to create tmux session for %s", ticket_id)
            await websocket.send_text("\r\n\x1b[31m[tmux session failed]\x1b[0m\r\n")
            await websocket.close()
            return

        try:
            master_fd, child_pid = tmux.attach_pty(ticket_id)
        except Exception:
            logger.exception("Failed to attach pty for %s", ticket_id)
            await websocket.send_text("\r\n\x1b[31m[pty attach failed]\x1b[0m\r\n")
            await websocket.close()
            return

        try:
            await _bridge(websocket, master_fd)
        except WebSocketDisconnect:
            logger.debug("WebSocket disconnected for ticket %s", ticket_id)
        except Exception:
            logger.exception("Terminal error for ticket %s", ticket_id)
        finally:
            os.close(master_fd)
            # Kill the tmux attach process
            try:
                os.kill(child_pid, 9)
                os.waitpid(child_pid, 0)
            except OSError:
                pass

    return router


async def _bridge(websocket: WebSocket, master_fd: int) -> None:
    """Bridge WebSocket ↔ pty bidirectionally."""
    loop = asyncio.get_event_loop()

    async def read_pty() -> None:
        """Read from pty and send to WebSocket."""
        while True:
            try:
                data = await loop.run_in_executor(None, _read_pty_blocking, master_fd)
                if not data:
                    break
                await websocket.send_bytes(data)
            except OSError:
                break

    async def write_pty() -> None:
        """Read from WebSocket and write to pty."""
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            # Handle text messages (could be resize or input)
            text = message.get("text")
            if text is not None:
                try:
                    msg = json.loads(text)
                    if msg.get("type") == "resize":
                        _resize_pty(master_fd, msg["cols"], msg["rows"])
                        continue
                except (json.JSONDecodeError, KeyError):
                    # Plain text input
                    os.write(master_fd, text.encode())
                    continue

            # Handle binary data
            data = message.get("bytes")
            if data is not None:
                os.write(master_fd, data)

    read_task = asyncio.create_task(read_pty())
    write_task = asyncio.create_task(write_pty())

    try:
        _done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except Exception:
        read_task.cancel()
        write_task.cancel()


def _read_pty_blocking(master_fd: int) -> bytes:
    """Read from pty (blocking). Returns empty bytes on EOF."""
    try:
        return os.read(master_fd, BUF_SIZE)
    except OSError:
        return b""


def _resize_pty(master_fd: int, cols: int, rows: int) -> None:
    """Resize the pty using TIOCSWINSZ."""
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
