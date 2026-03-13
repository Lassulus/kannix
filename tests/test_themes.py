"""Tests for CSS themes and theme chooser."""

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


async def test_static_css_themes_served(client: AsyncClient) -> None:
    """Each theme CSS file should be servable at /static/themes/<name>.css."""
    for theme in ["midnight", "light", "solarized", "nord", "dracula"]:
        resp = await client.get(f"/static/themes/{theme}.css")
        assert resp.status_code == 200, f"Theme {theme} not found"
        assert "text/css" in resp.headers["content-type"]


async def test_base_css_served(client: AsyncClient) -> None:
    """Base CSS (layout) should be served at /static/base.css."""
    resp = await client.get("/static/base.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


async def test_board_includes_theme_link(client: AsyncClient, auth: AuthManager) -> None:
    """Board page should include a link to the current theme CSS."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token})
    assert resp.status_code == 200
    assert "/static/themes/" in resp.text
    assert '<link rel="stylesheet"' in resp.text


async def test_board_includes_base_css(client: AsyncClient, auth: AuthManager) -> None:
    """Board page should include the base layout CSS."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token})
    assert "/static/base.css" in resp.text


async def test_board_includes_theme_chooser(client: AsyncClient, auth: AuthManager) -> None:
    """Board page should include a theme chooser select element."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token})
    assert "theme-chooser" in resp.text
    assert "<select" in resp.text


async def test_default_theme_is_midnight(client: AsyncClient, auth: AuthManager) -> None:
    """Without a cookie, the default theme should be midnight."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token})
    assert "/static/themes/midnight.css" in resp.text


async def test_theme_cookie_selects_theme(client: AsyncClient, auth: AuthManager) -> None:
    """Setting a theme cookie should change which CSS is loaded."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token, "theme": "nord"})
    assert "/static/themes/nord.css" in resp.text


async def test_invalid_theme_cookie_falls_back_to_default(
    client: AsyncClient, auth: AuthManager
) -> None:
    """An invalid theme cookie should fall back to midnight."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get("/board", cookies={"token": user.token, "theme": "nonexistent"})
    assert "/static/themes/midnight.css" in resp.text


async def test_login_page_has_theme_css(client: AsyncClient) -> None:
    """Login page should also include theme CSS."""
    resp = await client.get("/login")
    assert "/static/themes/" in resp.text
    assert "/static/base.css" in resp.text


async def test_ticket_page_has_theme_css(client: AsyncClient, auth: AuthManager) -> None:
    """Ticket detail page should include theme CSS."""
    from kannix.tickets import TicketManager

    user = auth.create_user("alice", "pass", is_admin=False)
    mgr = TicketManager(
        StateManager(
            client._transport.app.state.deps.state_manager._path  # type: ignore[union-attr]
        ),
        client._transport.app.state.deps.config,  # type: ignore[union-attr]
    )
    ticket = mgr.create("themed ticket", "")
    resp = await client.get(f"/ticket/{ticket.id}", cookies={"token": user.token})
    assert "/static/themes/" in resp.text


async def test_theme_css_has_css_variables(client: AsyncClient) -> None:
    """Theme CSS files should define CSS custom properties on :root."""
    resp = await client.get("/static/themes/midnight.css")
    assert ":root" in resp.text
    assert "--bg-primary" in resp.text
    assert "--accent" in resp.text
