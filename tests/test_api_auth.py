"""Tests for auth API endpoints."""

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


async def test_login_success(client: AsyncClient, auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    response = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["username"] == "alice"


async def test_login_wrong_password(client: AsyncClient, auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    response = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_login_unknown_user(client: AsyncClient):
    response = await client.post(
        "/api/auth/login", json={"username": "nobody", "password": "pass"}
    )
    assert response.status_code == 401


async def test_protected_endpoint_without_token(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_protected_endpoint_with_valid_token(client: AsyncClient, auth: AuthManager):
    user = auth.create_user("alice", "secret", is_admin=False)
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user.token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice"


async def test_protected_endpoint_with_invalid_token(client: AsyncClient):
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer bogus-token"})
    assert response.status_code == 401


async def test_setup_creates_admin_when_no_users(client: AsyncClient):
    """POST /api/auth/setup creates admin when no users exist."""
    resp = await client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "s3cure!pass"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "admin"
    assert data["is_admin"] is True
    assert "token" in data


async def test_setup_fails_when_users_exist(client: AsyncClient, auth: AuthManager):
    """POST /api/auth/setup fails when users already exist."""
    auth.create_user("existing", "pass", is_admin=False)
    resp = await client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "s3cure!pass"},
    )
    assert resp.status_code == 403
