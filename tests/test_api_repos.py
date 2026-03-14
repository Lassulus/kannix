"""Tests for repo API endpoints."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from kannix.app import create_app
from kannix.auth import AuthManager
from kannix.git import GitManager
from kannix.state import StateManager
from kannix.tickets import TicketManager

if TYPE_CHECKING:
    from pathlib import Path

    from kannix.config import KannixConfig


def _is_sandbox() -> bool:
    return bool(os.environ.get("NIX_BUILD_TOP"))


def _init_test_repo(path: Path) -> Path:
    """Create a bare git repo with one commit for testing."""
    import subprocess

    work = path / "work"
    work.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "test@test.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "Test"],
        capture_output=True,
        check=True,
    )
    (work / "README.md").write_text("# Test\n")
    subprocess.run(["git", "-C", str(work), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "init"],
        capture_output=True,
        check=True,
    )
    bare = path / "bare.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)],
        capture_output=True,
        check=True,
    )
    return bare


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def config(tmp_path: Path) -> KannixConfig:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(
        json.dumps(
            {
                "columns": ["Backlog", "Done"],
                "repos_dir": str(tmp_path / "repos"),
                "worktree_dir": str(tmp_path / "worktrees"),
            }
        )
    )
    from kannix.config import load_config

    return load_config(config_path)


@pytest.fixture
def auth(state_manager: StateManager) -> AuthManager:
    return AuthManager(state_manager)


@pytest.fixture
def user_token(auth: AuthManager) -> str:
    return auth.create_user("testuser", "pass", is_admin=False).token


@pytest.fixture
def git_manager(tmp_path: Path, state_manager: StateManager) -> GitManager:
    repos_dir = tmp_path / "repos"
    worktree_dir = tmp_path / "worktrees"
    repos_dir.mkdir()
    worktree_dir.mkdir()
    return GitManager(repos_dir=repos_dir, worktree_dir=worktree_dir, state_manager=state_manager)


@pytest.fixture
async def client(
    config: KannixConfig, state_manager: StateManager, git_manager: GitManager
) -> AsyncClient:
    app = create_app(config=config, state_manager=state_manager, git_manager=git_manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_list_repos_empty(client: AsyncClient, user_token: str) -> None:
    """GET /api/repos returns empty list initially."""
    resp = await client.get("/api/repos", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_list_repos_requires_auth(client: AsyncClient) -> None:
    """GET /api/repos requires authentication."""
    resp = await client.get("/api/repos")
    assert resp.status_code == 401


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_clone_and_list_repo(client: AsyncClient, user_token: str, tmp_path: Path) -> None:
    """POST /api/repos clones a repo, GET /api/repos lists it."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "testrepo"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "testrepo"
    assert data["default_branch"] == "main"
    assert data["id"]

    # List
    resp = await client.get("/api/repos", headers=_auth(user_token))
    assert resp.status_code == 200
    repos = resp.json()
    assert len(repos) == 1
    assert repos[0]["name"] == "testrepo"


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_get_repo(client: AsyncClient, user_token: str, tmp_path: Path) -> None:
    """GET /api/repos/{id} returns a specific repo."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "testrepo"},
        headers=_auth(user_token),
    )
    repo_id = resp.json()["id"]

    resp = await client.get(f"/api/repos/{repo_id}", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "testrepo"


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_get_repo_not_found(client: AsyncClient, user_token: str) -> None:
    """GET /api/repos/{id} returns 404 for unknown ID."""
    resp = await client.get("/api/repos/nonexistent", headers=_auth(user_token))
    assert resp.status_code == 404


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_delete_repo(client: AsyncClient, user_token: str, tmp_path: Path) -> None:
    """DELETE /api/repos/{id} removes a repo."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "testrepo"},
        headers=_auth(user_token),
    )
    repo_id = resp.json()["id"]

    resp = await client.delete(f"/api/repos/{repo_id}", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    resp = await client.get("/api/repos", headers=_auth(user_token))
    assert resp.json() == []


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_delete_repo_not_found(client: AsyncClient, user_token: str) -> None:
    """DELETE /api/repos/{id} returns 404 for unknown ID."""
    resp = await client.delete("/api/repos/nonexistent", headers=_auth(user_token))
    assert resp.status_code == 404


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_assign_repo_to_ticket(
    client: AsyncClient,
    user_token: str,
    tmp_path: Path,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """POST /api/repos/assign assigns a repo and creates worktree."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "myrepo"},
        headers=_auth(user_token),
    )
    repo_id = resp.json()["id"]

    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    resp = await client.post(
        "/api/repos/assign",
        json={"repo_id": repo_id, "ticket_id": ticket.id},
        headers=_auth(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "assigned"

    # Verify in state
    state = state_manager.load()
    assert repo_id in state.tickets[ticket.id].repos

    # Verify worktree exists
    wt_path = tmp_path / "worktrees" / ticket.dir_name / "myrepo"
    assert wt_path.exists()


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_unassign_repo_from_ticket(
    client: AsyncClient,
    user_token: str,
    tmp_path: Path,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """POST /api/repos/unassign removes assignment and worktree."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "myrepo"},
        headers=_auth(user_token),
    )
    repo_id = resp.json()["id"]

    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    # Assign
    await client.post(
        "/api/repos/assign",
        json={"repo_id": repo_id, "ticket_id": ticket.id},
        headers=_auth(user_token),
    )

    # Unassign
    resp = await client.post(
        "/api/repos/unassign",
        json={"repo_id": repo_id, "ticket_id": ticket.id},
        headers=_auth(user_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "unassigned"

    state = state_manager.load()
    assert repo_id not in state.tickets[ticket.id].repos


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_assign_nonexistent_ticket(
    client: AsyncClient, user_token: str, tmp_path: Path
) -> None:
    """POST /api/repos/assign returns 404 for missing ticket."""
    source = _init_test_repo(tmp_path / "source")
    resp = await client.post(
        "/api/repos",
        json={"url": f"file://{source}", "name": "myrepo"},
        headers=_auth(user_token),
    )
    repo_id = resp.json()["id"]

    resp = await client.post(
        "/api/repos/assign",
        json={"repo_id": repo_id, "ticket_id": "nonexistent"},
        headers=_auth(user_token),
    )
    assert resp.status_code == 404


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_assign_nonexistent_repo(
    client: AsyncClient,
    user_token: str,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """POST /api/repos/assign returns 404 for missing repo."""
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test", "desc")

    resp = await client.post(
        "/api/repos/assign",
        json={"repo_id": "nonexistent", "ticket_id": ticket.id},
        headers=_auth(user_token),
    )
    assert resp.status_code == 404
