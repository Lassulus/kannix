"""Tests for terminal-related views."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from kannix.app import create_app
from kannix.auth import AuthManager
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
    config_path.write_text(json.dumps({"columns": ["Backlog", "Done"]}))
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def auth(state_manager: StateManager) -> AuthManager:
    return AuthManager(state_manager)


@pytest.fixture
def ticket_mgr(state_manager: StateManager, config: KannixConfig) -> TicketManager:
    return TicketManager(state_manager, config)


@pytest.fixture
async def client(config: KannixConfig, state_manager: StateManager) -> AsyncClient:
    app = create_app(config=config, state_manager=state_manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


async def test_ticket_detail_includes_xterm(
    client: AsyncClient,
    auth: AuthManager,
    ticket_mgr: TicketManager,
):
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("Test terminal", "desc")
    resp = await client.get(
        f"/ticket/{ticket.id}",
        cookies={"token": user.token},
    )
    assert resp.status_code == 200
    assert "xterm.min.js" in resp.text
    assert "xterm.min.css" in resp.text
    assert "addon-fit" in resp.text


async def test_ticket_detail_has_websocket_url(
    client: AsyncClient,
    auth: AuthManager,
    ticket_mgr: TicketManager,
):
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("WS test", "")
    resp = await client.get(
        f"/ticket/{ticket.id}",
        cookies={"token": user.token},
    )
    assert resp.status_code == 200
    assert f"/ws/terminal/{ticket.id}" in resp.text
    assert f"token={user.token}" in resp.text


async def test_ticket_detail_unauthenticated_redirects(
    client: AsyncClient,
    ticket_mgr: TicketManager,
):
    ticket = ticket_mgr.create("Auth test", "")
    resp = await client.get(f"/ticket/{ticket.id}", follow_redirects=False)
    assert resp.status_code in (302, 307)


async def test_ticket_detail_not_found(
    client: AsyncClient,
    auth: AuthManager,
):
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get(
        "/ticket/nonexistent",
        cookies={"token": user.token},
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/board"
