"""Tests for hook execution engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kannix.config import HooksConfig
from kannix.hooks import HookExecutor

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_marker(tmp_path: Path) -> Path:
    """A file path hooks can write to as proof of execution."""
    return tmp_path / "marker"


async def test_on_create_hook_runs(tmp_marker: Path):
    hooks = HooksConfig(on_create=f"echo $TICKET_ID > {tmp_marker}")
    executor = HookExecutor(hooks)
    await executor.on_create(ticket_id="t123", ticket_title="Test", ticket_column="Backlog")
    assert tmp_marker.read_text().strip() == "t123"


async def test_on_create_receives_env_vars(tmp_marker: Path):
    hooks = HooksConfig(
        on_create=f'echo "$TICKET_ID|$TICKET_TITLE|$TICKET_COLUMN|$TMUX_SESSION" > {tmp_marker}'
    )
    executor = HookExecutor(hooks)
    await executor.on_create(ticket_id="t1", ticket_title="My Ticket", ticket_column="Backlog")
    parts = tmp_marker.read_text().strip().split("|")
    assert parts[0] == "t1"
    assert parts[1] == "My Ticket"
    assert parts[2] == "Backlog"
    assert parts[3] == "t1"  # TMUX_SESSION defaults to ticket_id


async def test_on_delete_hook_runs(tmp_marker: Path):
    hooks = HooksConfig(on_delete=f"echo deleted_$TICKET_ID > {tmp_marker}")
    executor = HookExecutor(hooks)
    await executor.on_delete(ticket_id="t456", ticket_title="Bye", ticket_column="Done")
    assert tmp_marker.read_text().strip() == "deleted_t456"


async def test_on_move_hook_runs(tmp_marker: Path):
    hooks = HooksConfig(
        on_move={
            "Backlog->In Progress": f"echo moved > {tmp_marker}",
        }
    )
    executor = HookExecutor(hooks)
    await executor.on_move(
        ticket_id="t1",
        ticket_title="T",
        from_column="Backlog",
        to_column="In Progress",
    )
    assert tmp_marker.read_text().strip() == "moved"


async def test_on_move_receives_env_vars(tmp_marker: Path):
    hooks = HooksConfig(
        on_move={
            "Backlog->Done": f'echo "$TICKET_PREV_COLUMN|$TICKET_COLUMN" > {tmp_marker}',
        }
    )
    executor = HookExecutor(hooks)
    await executor.on_move(
        ticket_id="t1",
        ticket_title="T",
        from_column="Backlog",
        to_column="Done",
    )
    assert tmp_marker.read_text().strip() == "Backlog|Done"


async def test_on_move_no_matching_hook_is_noop(tmp_marker: Path):
    hooks = HooksConfig(
        on_move={
            "Backlog->Done": f"echo should_not_run > {tmp_marker}",
        }
    )
    executor = HookExecutor(hooks)
    await executor.on_move(
        ticket_id="t1",
        ticket_title="T",
        from_column="Backlog",
        to_column="In Progress",
    )
    assert not tmp_marker.exists()


async def test_failing_hook_does_not_raise(tmp_marker: Path):
    hooks = HooksConfig(on_create="exit 1")
    executor = HookExecutor(hooks)
    # Should not raise
    await executor.on_create(ticket_id="t1", ticket_title="T", ticket_column="Backlog")


async def test_no_hook_configured_is_noop():
    hooks = HooksConfig()
    executor = HookExecutor(hooks)
    # Should not raise
    await executor.on_create(ticket_id="t1", ticket_title="T", ticket_column="Backlog")
    await executor.on_delete(ticket_id="t1", ticket_title="T", ticket_column="Backlog")
    await executor.on_move(
        ticket_id="t1",
        ticket_title="T",
        from_column="Backlog",
        to_column="Done",
    )
