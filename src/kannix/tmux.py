"""Tmux session management."""

from __future__ import annotations

import logging
import os
import pty
import subprocess

logger = logging.getLogger(__name__)


class TmuxManager:
    """Manages tmux sessions for tickets."""

    def __init__(self, socket_name: str = "kannix") -> None:
        self._socket = socket_name

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a tmux command with our socket."""
        cmd = ["tmux", "-L", self._socket, *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def create_session(self, session_name: str) -> None:
        """Create a new detached tmux session.

        Idempotent: does nothing if session already exists.
        """
        if self.session_exists(session_name):
            return
        self._run("new-session", "-d", "-s", session_name)

    def kill_session(self, session_name: str) -> None:
        """Kill a tmux session. Does nothing if it doesn't exist."""
        if not self.session_exists(session_name):
            return
        self._run("kill-session", "-t", session_name)

    def session_exists(self, session_name: str) -> bool:
        """Check if a tmux session exists."""
        result = self._run("has-session", "-t", session_name, check=False)
        return result.returncode == 0

    def attach_pty(self, session_name: str) -> tuple[int, int]:
        """Attach to a tmux session via a pty.

        Returns:
            (master_fd, child_pid) tuple. The master_fd can be used
            to read/write terminal I/O.
        """
        child_pid, master_fd = pty.fork()
        if child_pid == 0:
            # Child process: exec tmux attach
            os.execlp(
                "tmux",
                "tmux",
                "-L",
                self._socket,
                "attach-session",
                "-t",
                session_name,
            )
        # Parent: return the master fd and child pid
        return master_fd, child_pid
