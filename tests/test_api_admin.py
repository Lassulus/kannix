"""Tests for admin user management API."""

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


@pytest.fixture
def admin_token(auth: AuthManager) -> str:
    user = auth.create_user("admin", "adminpass", is_admin=True)
    return user.token


@pytest.fixture
def user_token(auth: AuthManager) -> str:
    user = auth.create_user("regular", "userpass", is_admin=False)
    return user.token


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_user(client: AsyncClient, admin_token: str):
    response = await client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "pass123", "is_admin": False},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert "id" in data
    assert "token" in data
    assert data["is_admin"] is False


async def test_create_user_non_admin_forbidden(client: AsyncClient, user_token: str):
    response = await client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "pass123", "is_admin": False},
        headers=_auth_header(user_token),
    )
    assert response.status_code == 403


async def test_create_user_unauthenticated(client: AsyncClient):
    response = await client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "pass123", "is_admin": False},
    )
    assert response.status_code == 401


async def test_list_users(client: AsyncClient, admin_token: str, auth: AuthManager):
    auth.create_user("bob", "pass", is_admin=False)
    response = await client.get("/api/admin/users", headers=_auth_header(admin_token))
    assert response.status_code == 200
    users = response.json()
    # admin + bob
    assert len(users) == 2
    usernames = [u["username"] for u in users]
    assert "admin" in usernames
    assert "bob" in usernames
    # password_hash should not be exposed
    for u in users:
        assert "password_hash" not in u


async def test_delete_user(client: AsyncClient, admin_token: str, auth: AuthManager):
    bob = auth.create_user("bob", "pass", is_admin=False)
    response = await client.delete(f"/api/admin/users/{bob.id}", headers=_auth_header(admin_token))
    assert response.status_code == 200
    # Verify bob is gone
    list_resp = await client.get("/api/admin/users", headers=_auth_header(admin_token))
    usernames = [u["username"] for u in list_resp.json()]
    assert "bob" not in usernames


async def test_delete_nonexistent_user(client: AsyncClient, admin_token: str):
    response = await client.delete(
        "/api/admin/users/nonexistent", headers=_auth_header(admin_token)
    )
    assert response.status_code == 404


async def test_reset_token(client: AsyncClient, admin_token: str, auth: AuthManager):
    bob = auth.create_user("bob", "pass", is_admin=False)
    old_token = bob.token
    response = await client.post(
        f"/api/admin/users/{bob.id}/reset-token",
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] != old_token
    assert data["username"] == "bob"


async def test_non_admin_cannot_list(client: AsyncClient, user_token: str):
    response = await client.get("/api/admin/users", headers=_auth_header(user_token))
    assert response.status_code == 403
