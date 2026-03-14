"""Ticket CRUD management."""

from __future__ import annotations

import enum
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from kannix.state import TicketState

if TYPE_CHECKING:
    from kannix.config import KannixConfig
    from kannix.git import GitManager
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
        git_manager: GitManager | None = None,
    ) -> None:
        self._state = state_manager
        self._config = config
        self._hooks = hook_executor
        self._git = git_manager

    def create(self, title: str, description: str) -> TicketState:
        """Create a new ticket in the first column (sync, no hooks)."""
        from kannix.git import ticket_dir_name

        state = self._state.load()
        ticket_id = uuid.uuid4().hex
        ticket = TicketState(
            id=ticket_id,
            title=title,
            description=description,
            column=self._config.columns[0],
            assigned_to=None,
            dir_name=ticket_dir_name(ticket_id, title),
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

    def list_all(self, *, include_archived: bool = False) -> list[TicketState]:
        """List tickets, excluding archived by default."""
        state = self._state.load()
        tickets = list(state.tickets.values())
        if not include_archived:
            tickets = [t for t in tickets if not t.archived]
        return tickets

    def update(
        self,
        ticket_id: str,
        *,
        description: str | None = None,
        assigned_to: str | None | _Unset = UNSET,
    ) -> TicketState | None:
        """Update ticket fields. Returns None if ticket not found.

        Title is immutable (used for stable directory names).
        """
        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return None

        if description is not None:
            ticket = ticket.model_copy(update={"description": description})
        if not isinstance(assigned_to, _Unset):
            ticket = ticket.model_copy(update={"assigned_to": assigned_to})

        state.tickets[ticket_id] = ticket
        self._state.save(state)
        return ticket

    def delete(self, ticket_id: str) -> bool:
        """Delete a ticket (sync, no hooks). Backs up .pi and cleans up workspace. Returns True if deleted."""
        state = self._state.load()
        if ticket_id not in state.tickets:
            return False

        # Backup .pi before deleting
        self._backup_pi(ticket_id)

        # Clean up worktrees and workspace directory
        if self._git is not None:
            self._git.delete_ticket_workspace(ticket_id)

        del state.tickets[ticket_id]
        self._state.save(state)
        return True

    async def delete_async(self, ticket_id: str) -> bool:
        """Delete a ticket and run on_delete hook. Backs up .pi first."""
        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return False

        # Backup .pi before deleting
        self._backup_pi(ticket_id)

        # Clean up worktrees and workspace directory
        if self._git is not None:
            self._git.delete_ticket_workspace(ticket_id)

        del state.tickets[ticket_id]
        self._state.save(state)
        if self._hooks is not None:
            await self._hooks.on_delete(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                ticket_column=ticket.column,
            )
        return True

    def _backup_pi(self, ticket_id: str) -> Path | None:
        """Backup .pi directory for a ticket if git manager and archive dir are configured."""
        if self._git is None or self._config.archive_dir is None:
            return None
        archive_dir = Path(self._config.archive_dir)
        return self._git.backup_ticket_pi(ticket_id, archive_dir)

    def archive(self, ticket_id: str) -> TicketState | None:
        """Archive a ticket: backup .pi, mark as archived.

        Returns the updated ticket, or None if not found.
        """
        state = self._state.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return None

        # Backup .pi before archiving
        self._backup_pi(ticket_id)

        ticket = ticket.model_copy(update={"archived": True})
        state.tickets[ticket_id] = ticket
        self._state.save(state)
        return ticket

    async def archive_async(self, ticket_id: str) -> TicketState | None:
        """Archive a ticket and run on_delete hook (since it's being removed from active board)."""
        ticket = self.archive(ticket_id)
        if ticket is None:
            return None
        if self._hooks is not None:
            await self._hooks.on_delete(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                ticket_column=ticket.column,
            )
        return ticket

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
