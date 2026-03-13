"""Application dependencies container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kannix.auth import AuthManager
    from kannix.config import KannixConfig
    from kannix.git import GitManager
    from kannix.state import StateManager


@dataclass(frozen=True)
class AppDeps:
    """Shared application dependencies."""

    config: KannixConfig
    state_manager: StateManager
    auth_manager: AuthManager
    git_manager: GitManager | None = None
