"""State persistence with file locking."""

from __future__ import annotations

import fcntl
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path


class TicketState(BaseModel, extra="ignore"):
    """Persisted ticket data."""

    id: str
    title: str
    description: str
    column: str
    assigned_to: str | None
    repos: list[str] = []
    dir_name: str = ""


class RepoState(BaseModel, extra="ignore"):
    """Persisted git repository data."""

    id: str
    name: str
    url: str
    path: str
    default_branch: str = "main"


class UserState(BaseModel, extra="ignore"):
    """Persisted user data."""

    id: str
    username: str
    password_hash: str
    token: str
    is_admin: bool = False


class AppState(BaseModel, extra="ignore"):
    """Root application state."""

    tickets: dict[str, TicketState] = {}
    users: dict[str, UserState] = {}
    repos: dict[str, RepoState] = {}


class StateManager:
    """Manages loading and saving application state to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AppState:
        """Load state from disk.

        Returns:
            AppState from file, or empty AppState if file doesn't exist.

        Raises:
            ValueError: If the file contains corrupted JSON.
        """
        if not self._path.exists():
            return AppState()

        text = self._path.read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Corrupted state file: {e}") from e

        return AppState.model_validate(data)

    def save(self, state: AppState) -> None:
        """Save state to disk with file locking.

        Creates parent directories if needed.
        Uses fcntl exclusive lock to prevent concurrent write corruption.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = state.model_dump(mode="json")
        content = json.dumps(data, indent=2)

        with open(self._path, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(content)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
