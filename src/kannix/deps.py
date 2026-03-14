"""Application dependencies container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kannix.auth import AuthManager
    from kannix.config import KannixConfig
    from kannix.git import GitManager
    from kannix.hooks import HookExecutor
    from kannix.state import StateManager
    from kannix.tmux import TmuxManager


@dataclass(frozen=True)
class AppDeps:
    """Shared application dependencies."""

    config: KannixConfig
    state_manager: StateManager
    auth_manager: AuthManager
    git_manager: GitManager | None = None
    hook_executor: HookExecutor | None = None
    tmux_manager: TmuxManager | None = None
