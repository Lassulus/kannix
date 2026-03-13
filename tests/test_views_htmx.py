"""Tests for HTMX interactive endpoints."""

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
    config_path.write_text(json.dumps({"columns": ["Backlog", "In Progress", "Done"]}))
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


@pytest.fixture
def user_cookie(auth: AuthManager) -> dict[str, str]:
    user = auth.create_user("alice", "pass", is_admin=False)
    return {"token": user.token}


async def test_move_ticket_returns_partial(
    client: AsyncClient,
    user_cookie: dict[str, str],
    ticket_mgr: TicketManager,
):
    ticket = ticket_mgr.create("Move me", "")
    resp = await client.post(
        f"/htmx/tickets/{ticket.id}/move",
        data={"column": "In Progress"},
        cookies=user_cookie,
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "In Progress" in resp.text or "move" in resp.text.lower()


async def test_create_ticket_returns_card_partial(
    client: AsyncClient,
    user_cookie: dict[str, str],
):
    resp = await client.post(
        "/htmx/tickets",
        data={"title": "New task", "description": "Do stuff"},
        cookies=user_cookie,
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "New task" in resp.text
