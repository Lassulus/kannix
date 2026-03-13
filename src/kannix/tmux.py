"""Tmux session management."""

from __future__ import annotations

import logging
import os
import pty
import subprocess

logger = logging.getLogger(__name__)


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell use."""
    import shlex

    return shlex.quote(s)


class TmuxManager:
    """Manages tmux sessions for tickets."""

    def __init__(self, socket_name: str = "kannix") -> None:
        self._socket = socket_name

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a tmux command with our socket."""
        cmd = ["tmux", "-L", self._socket, *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _default_shell(self) -> str:
        """Get the user's default shell."""
        import pwd

        try:
            return pwd.getpwuid(os.getuid()).pw_shell
        except KeyError:
            return os.environ.get("SHELL", "/bin/sh")

    def create_session(
        self,
        session_name: str,
        env: dict[str, str] | None = None,
    ) -> None:
        """Create a new detached tmux session using the user's default shell.

        Idempotent: does nothing if session already exists.
        If env is provided, variables are passed via -e so the initial
        shell inherits them.
        """
        if self.session_exists(session_name):
            # Update env for future panes + export into running shell
            if env:
                for key, value in env.items():
                    self._run("set-environment", "-t", session_name, key, value)
                    # Also inject into running shell
                    self._run(
                        "send-keys",
                        "-t",
                        session_name,
                        f" export {key}={_shell_quote(value)}",
                        "Enter",
                    )
            return
        shell = self._default_shell()
        env_args: list[str] = []
        if env:
            for key, value in env.items():
                env_args.extend(["-e", f"{key}={value}"])
        self._run("new-session", "-d", "-s", session_name, *env_args, shell)

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
