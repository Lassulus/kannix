"""FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from kannix.api.auth import create_auth_router
from kannix.auth import AuthManager
from kannix.deps import AppDeps

if TYPE_CHECKING:
    from kannix.config import KannixConfig
    from kannix.state import StateManager


def create_app(
    config: KannixConfig | None = None,
    state_manager: StateManager | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Kannix", version="0.1.0")

    # Set up dependencies
    if config is not None and state_manager is not None:
        auth_manager = AuthManager(state_manager)
        deps = AppDeps(
            config=config,
            state_manager=state_manager,
            auth_manager=auth_manager,
        )
        app.state.deps = deps

        # Register routers
        app.include_router(create_auth_router(deps), prefix="/api/auth")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
