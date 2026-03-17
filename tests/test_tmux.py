"""Tests for tmux session manager."""

from __future__ import annotations

import os
import subprocess

import pytest

from kannix.tmux import TmuxManager


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

    os.close(fd)


def test_create_session_with_cwd(tmp_path):
    """create_session with cwd starts shell in that directory."""
    import uuid

    target_dir = tmp_path / "workdir"
    target_dir.mkdir()
    socket = f"kannix-test-cwd-{uuid.uuid4().hex[:8]}"
    # Use /bin/sh to avoid shell rc files overriding cwd
    mgr = TmuxManager(socket_name=socket)
    mgr._default_shell = lambda: "/bin/sh"  # type: ignore[method-assign]
    try:
        mgr.create_session("cwd-test", cwd=str(target_dir))
        assert mgr.session_exists("cwd-test")
        import time

        time.sleep(0.3)
        result = subprocess.run(
            [
                "tmux",
                "-L",
                socket,
                "display-message",
                "-t",
                "cwd-test",
                "-p",
                "#{pane_current_path}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert str(target_dir) in result.stdout
    finally:
        subprocess.run(
            ["tmux", "-L", socket, "kill-server"],
            capture_output=True,
        )
