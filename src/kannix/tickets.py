"""Ticket CRUD management."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from kannix.state import TicketState


class _Unset(enum.Enum):
    """Sentinel for unset optional fields."""

    UNSET = "UNSET"


UNSET = _Unset.UNSET

if TYPE_CHECKING:
    from kannix.config import KannixConfig
    from kannix.state import StateManager


class TicketManager:
    """Manages ticket CRUD operations."""

    def __init__(self, state_manager: StateManager, config: KannixConfig) -> None:
        self._state = state_manager
        self._config = config

    def create(self, title: str, description: str) -> TicketState:
        """Create a new ticket in the first column."""
        state = self._state.load()
        ticket = TicketState(
            id=uuid.uuid4().hex,
            title=title,
            description=description,
            column=self._config.columns[0],
            assigned_to=None,
        )
        state.tickets[ticket.id] = ticket
        self._state.save(state)
        return ticket

    def get(self, ticket_id: str) -> TicketState | None:
        """Get a ticket by ID."""
        state = self._state.load()
        return state.tickets.get(ticket_id)

    def list_all(self) -> list[TicketState]:
        """List all tickets."""
        state = self._state.load()
        return list(state.tickets.values())

    def update(
        self,
        ticket_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        assigned_to: str | None | _Unset = UNSET,
    ) -> TicketState | None:
        """Update ticket fields. Returns None if ticket not found."""
        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return None

        if title is not None:
            ticket = ticket.model_copy(update={"title": title})
        if description is not None:
            ticket = ticket.model_copy(update={"description": description})
        if not isinstance(assigned_to, _Unset):
            ticket = ticket.model_copy(update={"assigned_to": assigned_to})

        state.tickets[ticket_id] = ticket
        self._state.save(state)
        return ticket

    def delete(self, ticket_id: str) -> bool:
        """Delete a ticket. Returns True if deleted, False if not found."""
        state = self._state.load()
        if ticket_id not in state.tickets:
            return False
        del state.tickets[ticket_id]
        self._state.save(state)
        return True

    def move(self, ticket_id: str, column: str) -> TicketState | None:
        """Move a ticket to a different column.

        Raises:
            ValueError: If the column is not valid.
        """
        if column not in self._config.columns:
            raise ValueError(f"Invalid column: {column}")

        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return None

        ticket = ticket.model_copy(update={"column": column})
        state.tickets[ticket_id] = ticket
        self._state.save(state)
        return ticket
