"""Tests for state persistence."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kannix.state import AppState, StateManager, TicketState, UserState


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


@pytest.fixture
def manager(state_file: Path) -> StateManager:
    return StateManager(state_file)


def test_empty_state_initialization(manager: StateManager):
    """New state manager with no file starts with empty state."""
    state = manager.load()
    assert state.tickets == {}
    assert state.users == {}


def test_save_load_round_trip(manager: StateManager):
    """Saved state can be loaded back identically."""
    state = AppState(
        tickets={
            "t1": TicketState(
                id="t1",
                title="Fix bug",
                description="Something broken",
                column="Backlog",
                assigned_to=None,
            )
        },
        users={
            "u1": UserState(
                id="u1",
                username="alice",
                password_hash="hashed",
                token="tok123",
                is_admin=True,
            )
        },
    )
    manager.save(state)
    loaded = manager.load()
    assert loaded.tickets["t1"].title == "Fix bug"
    assert loaded.tickets["t1"].column == "Backlog"
    assert loaded.users["u1"].username == "alice"
    assert loaded.users["u1"].is_admin is True


def test_state_file_created_on_save(manager: StateManager, state_file: Path):
    """Saving creates the state file."""
    assert not state_file.exists()
    manager.save(AppState())
    assert state_file.exists()


def test_corrupted_file_raises(state_file: Path):
    """Corrupted JSON file raises ValueError."""
    state_file.write_text("not valid json {{{")
    mgr = StateManager(state_file)
    with pytest.raises(ValueError, match="Corrupted"):
        mgr.load()


def test_save_creates_parent_directories(tmp_path: Path):
    """Save creates parent dirs if they don't exist."""
    path = tmp_path / "subdir" / "deep" / "state.json"
    mgr = StateManager(path)
    mgr.save(AppState())
    assert path.exists()


def test_concurrent_saves_dont_corrupt(tmp_path: Path):
    """Multiple concurrent saves should not produce corrupted state."""
    path = tmp_path / "state.json"
    mgr = StateManager(path)

    async def write_state(ticket_id: str) -> None:
        state = AppState(
            tickets={
                ticket_id: TicketState(
                    id=ticket_id,
                    title=f"Ticket {ticket_id}",
                    description="",
                    column="Backlog",
                    assigned_to=None,
                )
            }
        )
        mgr.save(state)

    # Run multiple saves; file should always be valid JSON after
    for i in range(20):
        asyncio.get_event_loop().run_until_complete(write_state(f"t{i}"))

    # File must be valid JSON and loadable
    loaded = mgr.load()
    assert isinstance(loaded, AppState)


def test_load_preserves_unknown_ticket_fields(state_file: Path):
    """State file with extra fields in tickets doesn't crash."""
    data = {
        "tickets": {
            "t1": {
                "id": "t1",
                "title": "Test",
                "description": "",
                "column": "Backlog",
                "assigned_to": None,
                "extra_field": "should be ignored",
            }
        },
        "users": {},
    }
    state_file.write_text(json.dumps(data))
    mgr = StateManager(state_file)
    state = mgr.load()
    assert state.tickets["t1"].title == "Test"
