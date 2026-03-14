"""Tests for ticket API endpoints."""

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
    config_path.write_text(json.dumps({"columns": ["Backlog", "In Progress", "Review", "Done"]}))
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def auth(state_manager: StateManager) -> AuthManager:
    return AuthManager(state_manager)


@pytest.fixture
def user_token(auth: AuthManager) -> str:
    return auth.create_user("testuser", "pass", is_admin=False).token


@pytest.fixture
async def client(config: KannixConfig, state_manager: StateManager) -> AsyncClient:
    app = create_app(config=config, state_manager=state_manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_ticket(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/tickets",
        json={"title": "Fix bug", "description": "It's broken"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix bug"
    assert data["description"] == "It's broken"
    assert data["column"] == "Backlog"
    assert "id" in data


async def test_create_ticket_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/api/tickets",
        json={"title": "Fix bug", "description": ""},
    )
    assert resp.status_code == 401


async def test_list_tickets(client: AsyncClient, user_token: str):
    await client.post(
        "/api/tickets",
        json={"title": "A", "description": ""},
        headers=_auth(user_token),
    )
    await client.post(
        "/api/tickets",
        json={"title": "B", "description": ""},
        headers=_auth(user_token),
    )
    resp = await client.get("/api/tickets", headers=_auth(user_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_get_ticket(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Get me", "description": "desc"},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.get(f"/api/tickets/{ticket_id}", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get me"


async def test_get_nonexistent_ticket(client: AsyncClient, user_token: str):
    resp = await client.get("/api/tickets/nonexistent", headers=_auth(user_token))
    assert resp.status_code == 404


async def test_update_ticket(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Old", "description": "old desc"},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.put(
        f"/api/tickets/{ticket_id}",
        json={"description": "new desc"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Old"  # title is immutable
    assert resp.json()["description"] == "new desc"


async def test_update_nonexistent_ticket(client: AsyncClient, user_token: str):
    resp = await client.put(
        "/api/tickets/nonexistent",
        json={"description": "X"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 404


async def test_delete_ticket(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Delete me", "description": ""},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/tickets/{ticket_id}", headers=_auth(user_token))
    assert resp.status_code == 200
    # Verify it's gone
    get_resp = await client.get(f"/api/tickets/{ticket_id}", headers=_auth(user_token))
    assert get_resp.status_code == 404


async def test_delete_nonexistent_ticket(client: AsyncClient, user_token: str):
    resp = await client.delete("/api/tickets/nonexistent", headers=_auth(user_token))
    assert resp.status_code == 404


async def test_move_ticket(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Move me", "description": ""},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.post(
        f"/api/tickets/{ticket_id}/move",
        json={"column": "In Progress"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["column"] == "In Progress"


async def test_move_ticket_invalid_column(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Bad move", "description": ""},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.post(
        f"/api/tickets/{ticket_id}/move",
        json={"column": "Nonexistent"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 400


async def test_move_nonexistent_ticket(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/tickets/nonexistent/move",
        json={"column": "Backlog"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 404


async def test_archive_ticket(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Archive me", "description": ""},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    resp = await client.post(
        f"/api/tickets/{ticket_id}/archive",
        headers=_auth(user_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "archived"
    assert data["archived"] is True

    # Should not appear in default listing
    list_resp = await client.get("/api/tickets", headers=_auth(user_token))
    assert all(t["id"] != ticket_id for t in list_resp.json())

    # Should appear with include_archived
    list_resp2 = await client.get(
        "/api/tickets?include_archived=true", headers=_auth(user_token)
    )
    assert any(t["id"] == ticket_id for t in list_resp2.json())


async def test_archive_nonexistent_ticket(client: AsyncClient, user_token: str):
    resp = await client.post(
        "/api/tickets/nonexistent/archive",
        headers=_auth(user_token),
    )
    assert resp.status_code == 404


async def test_archived_ticket_still_gettable(client: AsyncClient, user_token: str):
    create_resp = await client.post(
        "/api/tickets",
        json={"title": "Archived but gettable", "description": ""},
        headers=_auth(user_token),
    )
    ticket_id = create_resp.json()["id"]
    await client.post(f"/api/tickets/{ticket_id}/archive", headers=_auth(user_token))
    resp = await client.get(f"/api/tickets/{ticket_id}", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["archived"] is True
