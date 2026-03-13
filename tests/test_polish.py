"""Tests for polish: error handling, validation, reconnection."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from kannix.app import create_app
from kannix.auth import AuthManager
from kannix.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path

    from kannix.config import KannixConfig


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def config(tmp_path: Path) -> KannixConfig:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo", "Done"]}))
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def auth(state_manager: StateManager) -> AuthManager:
    return AuthManager(state_manager)


@pytest.fixture
async def client(config: KannixConfig, state_manager: StateManager) -> AsyncClient:
    app = create_app(config=config, state_manager=state_manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


async def test_create_ticket_empty_title_rejected(client: AsyncClient, auth: AuthManager):
    """Tickets with empty titles should be rejected."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.post(
        "/api/tickets",
        json={"title": "", "description": "desc"},
        headers={"Authorization": f"Bearer {user.token}"},
    )
    assert resp.status_code == 422


async def test_create_ticket_whitespace_title_rejected(client: AsyncClient, auth: AuthManager):
    """Tickets with whitespace-only titles should be rejected."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.post(
        "/api/tickets",
        json={"title": "   ", "description": "desc"},
        headers={"Authorization": f"Bearer {user.token}"},
    )
    assert resp.status_code == 422


async def test_nonexistent_route_returns_404(client: AsyncClient):
    resp = await client.get("/nonexistent")
    assert resp.status_code == 404


async def test_invalid_json_body_returns_422(client: AsyncClient, auth: AuthManager):
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.post(
        "/api/tickets",
        content="not json",
        headers={
            "Authorization": f"Bearer {user.token}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 422


async def test_ticket_detail_has_reconnection_script(client: AsyncClient, auth: AuthManager):
    """Terminal page should have reconnection logic."""
    user = auth.create_user("alice", "pass", is_admin=False)
    from kannix.tickets import TicketManager

    mgr = TicketManager(
        StateManager(client._transport.app.state.deps.state_manager._path),  # type: ignore[union-attr]
        client._transport.app.state.deps.config,  # type: ignore[union-attr]
    )
    ticket = mgr.create("reconnect test", "")
    resp = await client.get(
        f"/ticket/{ticket.id}",
        cookies={"token": user.token},
    )
    assert resp.status_code == 200
    assert "onclose" in resp.text
