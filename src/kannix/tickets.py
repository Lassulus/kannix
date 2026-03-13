"""Ticket CRUD management."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from kannix.state import TicketState

if TYPE_CHECKING:
    from kannix.config import KannixConfig
    from kannix.hooks import HookExecutor
    from kannix.state import StateManager


class _Unset(enum.Enum):
    """Sentinel for unset optional fields."""

    UNSET = "UNSET"


UNSET = _Unset.UNSET


class TicketManager:
    """Manages ticket CRUD operations."""

    def __init__(
        self,
        state_manager: StateManager,
        config: KannixConfig,
        hook_executor: HookExecutor | None = None,
    ) -> None:
        self._state = state_manager
        self._config = config
        self._hooks = hook_executor

    def create(self, title: str, description: str) -> TicketState:
        """Create a new ticket in the first column (sync, no hooks)."""
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

    async def create_async(self, title: str, description: str) -> TicketState:
        """Create a new ticket and run on_create hook."""
        ticket = self.create(title, description)
        if self._hooks is not None:
            await self._hooks.on_create(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                ticket_column=ticket.column,
            )
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
        """Delete a ticket (sync, no hooks). Returns True if deleted."""
        state = self._state.load()
        if ticket_id not in state.tickets:
            return False
        del state.tickets[ticket_id]
        self._state.save(state)
        return True

    async def delete_async(self, ticket_id: str) -> bool:
        """Delete a ticket and run on_delete hook."""
        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return False
        del state.tickets[ticket_id]
        self._state.save(state)
        if self._hooks is not None:
            await self._hooks.on_delete(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                ticket_column=ticket.column,
            )
        return True

    def move(self, ticket_id: str, column: str) -> TicketState | None:
        """Move a ticket (sync, no hooks).

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

    async def move_async(self, ticket_id: str, column: str) -> TicketState | None:
        """Move a ticket and run on_move hook.

        Raises:
            ValueError: If the column is not valid.
        """
        if column not in self._config.columns:
            raise ValueError(f"Invalid column: {column}")

        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return None

        old_column = ticket.column
        ticket = ticket.model_copy(update={"column": column})
        state.tickets[ticket_id] = ticket
        self._state.save(state)

        if self._hooks is not None:
            await self._hooks.on_move(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                from_column=old_column,
                to_column=column,
            )
        return ticket
