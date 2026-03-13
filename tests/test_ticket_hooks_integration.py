"""Integration tests: ticket lifecycle triggers hooks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from kannix.hooks import HookExecutor
from kannix.state import StateManager
from kannix.tickets import TicketManager

if TYPE_CHECKING:
    from pathlib import Path

    from kannix.config import KannixConfig


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def marker(tmp_path: Path) -> Path:
    return tmp_path / "hook_marker"


@pytest.fixture
def config_with_hooks(tmp_path: Path, marker: Path) -> KannixConfig:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(
        json.dumps(
            {
                "columns": ["Backlog", "In Progress", "Done"],
                "hooks": {
                    "on_create": f"echo create:$TICKET_ID >> {marker}",
                    "on_move": {
                        "Backlog->In Progress": f"echo move >> {marker}",
                    },
                    "on_delete": f"echo delete:$TICKET_ID >> {marker}",
                },
            }
        )
    )
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def hook_executor(config_with_hooks: KannixConfig) -> HookExecutor:
    return HookExecutor(config_with_hooks.hooks)


@pytest.fixture
def tickets(
    state_manager: StateManager,
    config_with_hooks: KannixConfig,
    hook_executor: HookExecutor,
) -> TicketManager:
    return TicketManager(state_manager, config_with_hooks, hook_executor=hook_executor)


async def test_create_triggers_on_create(tickets: TicketManager, marker: Path):
    ticket = await tickets.create_async("Test ticket", "desc")
    lines = marker.read_text().strip().split("\n")
    assert f"create:{ticket.id}" in lines


async def test_move_triggers_on_move(tickets: TicketManager, marker: Path):
    ticket = await tickets.create_async("Move ticket", "")
    await tickets.move_async(ticket.id, "In Progress")
    lines = marker.read_text().strip().split("\n")
    assert "move" in lines


async def test_delete_triggers_on_delete(tickets: TicketManager, marker: Path):
    ticket = await tickets.create_async("Delete ticket", "")
    await tickets.delete_async(ticket.id)
    lines = marker.read_text().strip().split("\n")
    assert f"delete:{ticket.id}" in lines


async def test_move_no_hook_configured_still_moves(tickets: TicketManager, marker: Path):
    """Moving to a column with no hook configured still works."""
    ticket = await tickets.create_async("No hook move", "")
    result = await tickets.move_async(ticket.id, "Done")
    assert result is not None
    assert result.column == "Done"
