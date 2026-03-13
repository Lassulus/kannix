"""Hook execution engine for ticket lifecycle events."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kannix.config import HooksConfig

logger = logging.getLogger(__name__)


class HookExecutor:
    """Executes configured shell commands on ticket lifecycle events."""

    def __init__(self, hooks: HooksConfig) -> None:
        self._hooks = hooks

    async def on_create(self, *, ticket_id: str, ticket_title: str, ticket_column: str) -> None:
        """Run on_create hook if configured."""
        if self._hooks.on_create is None:
            return
        env = self._make_env(
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            ticket_column=ticket_column,
        )
        await self._run(self._hooks.on_create, env)

    async def on_delete(self, *, ticket_id: str, ticket_title: str, ticket_column: str) -> None:
        """Run on_delete hook if configured."""
        if self._hooks.on_delete is None:
            return
        env = self._make_env(
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            ticket_column=ticket_column,
        )
        await self._run(self._hooks.on_delete, env)

    async def on_move(
        self,
        *,
        ticket_id: str,
        ticket_title: str,
        from_column: str,
        to_column: str,
    ) -> None:
        """Run on_move hook for the specific transition if configured."""
        key = f"{from_column}->{to_column}"
        command = self._hooks.on_move.get(key)
        if command is None:
            return
        env = self._make_env(
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            ticket_column=to_column,
            ticket_prev_column=from_column,
        )
        await self._run(command, env)

    def _make_env(
        self,
        *,
        ticket_id: str,
        ticket_title: str,
        ticket_column: str,
        ticket_prev_column: str = "",
    ) -> dict[str, str]:
        """Build environment variables for hook execution."""
        env = dict(os.environ)
        env.update(
            {
                "TICKET_ID": ticket_id,
                "TICKET_TITLE": ticket_title,
                "TICKET_COLUMN": ticket_column,
                "TICKET_PREV_COLUMN": ticket_prev_column,
                "TMUX_SESSION": ticket_id,
            }
        )
        return env

    async def _run(self, command: str, env: dict[str, str]) -> None:
        """Execute a shell command, logging errors but never raising."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    "Hook command failed (rc=%d): %s\nstderr: %s",
                    proc.returncode,
                    command,
                    stderr.decode(errors="replace"),
                )
        except Exception:
            logger.exception("Hook execution error for command: %s", command)
