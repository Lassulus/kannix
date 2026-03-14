"""Tests for ticket CRUD logic."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from kannix.state import StateManager
from kannix.tickets import TicketManager

if TYPE_CHECKING:
    from pathlib import Path

    from kannix.config import KannixConfig


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def config(tmp_path: Path) -> KannixConfig:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Backlog", "In Progress", "Review", "Done"]}))
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def tickets(state_manager: StateManager, config: KannixConfig) -> TicketManager:
    return TicketManager(state_manager, config)


def test_create_ticket(tickets: TicketManager):
    ticket = tickets.create("Fix bug", "Something is broken")
    assert ticket.title == "Fix bug"
    assert ticket.description == "Something is broken"
    assert ticket.column == "Backlog"  # first column
    assert ticket.id != ""
    assert ticket.assigned_to is None


def test_create_ticket_generates_unique_ids(tickets: TicketManager):
    t1 = tickets.create("Ticket 1", "")
    t2 = tickets.create("Ticket 2", "")
    assert t1.id != t2.id


def test_create_ticket_persists(tickets: TicketManager, state_manager: StateManager):
    ticket = tickets.create("Persistent", "")
    state = state_manager.load()
    assert ticket.id in state.tickets
    assert state.tickets[ticket.id].title == "Persistent"


def test_get_ticket(tickets: TicketManager):
    created = tickets.create("Get me", "")
    found = tickets.get(created.id)
    assert found is not None
    assert found.title == "Get me"


def test_get_nonexistent_ticket(tickets: TicketManager):
    assert tickets.get("nonexistent") is None


def test_list_tickets(tickets: TicketManager):
    tickets.create("A", "")
    tickets.create("B", "")
    all_tickets = tickets.list_all()
    assert len(all_tickets) == 2
    titles = {t.title for t in all_tickets}
    assert titles == {"A", "B"}


def test_list_tickets_empty(tickets: TicketManager):
    assert tickets.list_all() == []


def test_update_ticket(tickets: TicketManager):
    ticket = tickets.create("Old title", "Old desc")
    updated = tickets.update(ticket.id, description="New desc")
    assert updated is not None
    assert updated.title == "Old title"  # title is immutable
    assert updated.description == "New desc"


def test_update_nonexistent_ticket(tickets: TicketManager):
    assert tickets.update("nonexistent", description="X") is None


def test_update_partial_fields(tickets: TicketManager):
    ticket = tickets.create("Title", "Desc")
    updated = tickets.update(ticket.id, description="New Desc")
    assert updated is not None
    assert updated.title == "Title"  # unchanged, immutable
    assert updated.description == "New Desc"


def test_delete_ticket(tickets: TicketManager):
    ticket = tickets.create("Delete me", "")
    assert tickets.delete(ticket.id) is True
    assert tickets.get(ticket.id) is None


def test_delete_nonexistent_ticket(tickets: TicketManager):
    assert tickets.delete("nonexistent") is False


def test_move_ticket_to_valid_column(tickets: TicketManager):
    ticket = tickets.create("Move me", "")
    assert ticket.column == "Backlog"
    moved = tickets.move(ticket.id, "In Progress")
    assert moved is not None
    assert moved.column == "In Progress"


def test_move_ticket_persists(tickets: TicketManager, state_manager: StateManager):
    ticket = tickets.create("Move persist", "")
    tickets.move(ticket.id, "Done")
    state = state_manager.load()
    assert state.tickets[ticket.id].column == "Done"


def test_move_ticket_to_invalid_column(tickets: TicketManager):
    ticket = tickets.create("Bad move", "")
    with pytest.raises(ValueError, match="Invalid column"):
        tickets.move(ticket.id, "Nonexistent Column")


def test_move_nonexistent_ticket(tickets: TicketManager):
    assert tickets.move("nonexistent", "Backlog") is None


def test_assign_ticket(tickets: TicketManager):
    ticket = tickets.create("Assign me", "")
    updated = tickets.update(ticket.id, assigned_to="alice")
    assert updated is not None
    assert updated.assigned_to == "alice"
