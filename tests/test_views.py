"""Tests for HTMX frontend views."""

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


async def test_root_redirects_to_login_unauthenticated(
    client: AsyncClient,
):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers.get("location", "")


async def test_login_page_renders(client: AsyncClient):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "login" in resp.text.lower()
    assert "<form" in resp.text.lower()


async def test_board_requires_auth(client: AsyncClient):
    resp = await client.get("/board", follow_redirects=False)
    assert resp.status_code in (302, 307)


async def test_board_renders_columns(client: AsyncClient, auth: AuthManager):
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get(
        "/board",
        cookies={"token": user.token},
    )
    assert resp.status_code == 200
    assert "Backlog" in resp.text
    assert "In Progress" in resp.text
    assert "Done" in resp.text


async def test_board_shows_ticket_titles(
    client: AsyncClient,
    auth: AuthManager,
    ticket_mgr: TicketManager,
):
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket_mgr.create("Fix the login bug", "desc")
    ticket_mgr.create("Add dark mode", "desc")
    resp = await client.get(
        "/board",
        cookies={"token": user.token},
    )
    assert resp.status_code == 200
    assert "Fix the login bug" in resp.text
    assert "Add dark mode" in resp.text


async def test_login_form_post_sets_cookie(client: AsyncClient, auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    resp = await client.post(
        "/login",
        data={"username": "alice", "password": "secret"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "token" in resp.cookies


async def test_login_form_post_bad_creds(client: AsyncClient, auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    resp = await client.post(
        "/login",
        data={"username": "alice", "password": "wrong"},
    )
    assert resp.status_code == 200
    assert "invalid" in resp.text.lower() or "error" in resp.text.lower()
