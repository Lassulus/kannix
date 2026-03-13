"""Tests for tmux session manager."""

from __future__ import annotations

import os
import subprocess

import pytest

from kannix.tmux import TmuxManager

# Skip in Nix sandbox (no tmux/pty available)
pytestmark = pytest.mark.skipif(
    os.environ.get("NIX_BUILD_TOP") is not None,
    reason="tmux tests require pty, not available in Nix sandbox",
)


@pytest.fixture
def tmux(tmp_path: object) -> TmuxManager:
    """Create a TmuxManager with a unique socket to avoid conflicts."""
    import uuid

    socket = f"kannix-test-{uuid.uuid4().hex[:8]}"
    mgr = TmuxManager(socket_name=socket)
    yield mgr  # type: ignore[misc]
    # Cleanup: kill the tmux server
    subprocess.run(
        ["tmux", "-L", socket, "kill-server"],
        capture_output=True,
    )


def test_create_session(tmux: TmuxManager):
    tmux.create_session("test-session")
    assert tmux.session_exists("test-session")


def test_session_not_exists(tmux: TmuxManager):
    assert not tmux.session_exists("nonexistent")


def test_kill_session(tmux: TmuxManager):
    tmux.create_session("kill-me")
    assert tmux.session_exists("kill-me")
    tmux.kill_session("kill-me")
    assert not tmux.session_exists("kill-me")


def test_kill_nonexistent_session(tmux: TmuxManager):
    # Should not raise
    tmux.kill_session("nonexistent")


def test_create_duplicate_session(tmux: TmuxManager):
    tmux.create_session("dup")
    # Creating again should not raise (idempotent)
    tmux.create_session("dup")
    assert tmux.session_exists("dup")


def test_get_pty_fd(tmux: TmuxManager):
    tmux.create_session("pty-test")
    fd, pid = tmux.attach_pty("pty-test")
    assert fd > 0
    assert pid > 0
    # Clean up
    import os

    os.close(fd)
