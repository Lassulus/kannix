"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from kannix.api.admin import create_admin_router
from kannix.api.auth import create_auth_router
from kannix.api.terminal import create_terminal_router
from kannix.api.tickets import create_tickets_router
from kannix.api.views import create_htmx_router, create_views_router
from kannix.auth import AuthManager
from kannix.deps import AppDeps
from kannix.tmux import TmuxManager

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
        app.include_router(create_admin_router(deps), prefix="/api/admin")
        app.include_router(create_tickets_router(deps), prefix="/api/tickets")

        from kannix.api.columns import create_columns_router

        app.include_router(create_columns_router(deps), prefix="/api")
        app.include_router(create_views_router(deps))
        app.include_router(create_htmx_router(deps), prefix="/htmx")

        # Terminal WebSocket
        tmux = TmuxManager()
        app.include_router(create_terminal_router(deps, tmux))

    # Mount static files
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
