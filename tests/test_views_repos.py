"""Tests for repo-related views and HTMX endpoints."""

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
        ["git", "-C", str(work), "commit", "-m", "init"], capture_output=True, check=True
    )
    bare = path / "bare.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)], capture_output=True, check=True
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


def _login_cookie(auth: AuthManager) -> dict[str, str]:
    user = auth.create_user("testuser", "pass", is_admin=False)
    return {"Cookie": f"token={user.token}"}


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_repos_page_renders(client: AsyncClient, auth: AuthManager) -> None:
    """GET /repos returns the repos page."""
    headers = _login_cookie(auth)
    resp = await client.get("/repos", headers=headers)
    assert resp.status_code == 200
    assert "Git Repositories" in resp.text
    assert "Clone Repository" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_repos_page_requires_auth(client: AsyncClient) -> None:
    """GET /repos redirects to login when unauthenticated."""
    resp = await client.get("/repos", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_repos_page_shows_cloned_repo(
    client: AsyncClient, auth: AuthManager, git_manager: GitManager, tmp_path: Path
) -> None:
    """Repos page lists cloned repos."""
    source = _init_test_repo(tmp_path / "source")
    git_manager.clone_repo(f"file://{source}", name="testrepo")

    headers = _login_cookie(auth)
    resp = await client.get("/repos", headers=headers)
    assert resp.status_code == 200
    assert "testrepo" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_ticket_page_shows_repos_section(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """Ticket detail page shows Repositories section when git is enabled."""
    headers = _login_cookie(auth)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    resp = await client.get(f"/ticket/{ticket.id}", headers=headers)
    assert resp.status_code == 200
    assert "Repositories" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_ticket_page_shows_assign_button(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
    git_manager: GitManager,
    tmp_path: Path,
) -> None:
    """Ticket page shows assign button for unassigned repos."""
    source = _init_test_repo(tmp_path / "source")
    git_manager.clone_repo(f"file://{source}", name="myrepo")

    headers = _login_cookie(auth)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    resp = await client.get(f"/ticket/{ticket.id}", headers=headers)
    assert resp.status_code == 200
    assert "+ myrepo" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_htmx_assign_repo(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
    git_manager: GitManager,
    tmp_path: Path,
) -> None:
    """HTMX assign-repo creates worktree and updates repos section."""
    source = _init_test_repo(tmp_path / "source")
    repo = git_manager.clone_repo(f"file://{source}", name="myrepo")

    user = auth.create_user("alice", "pass", is_admin=False)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    resp = await client.post(
        f"/htmx/tickets/{ticket.id}/assign-repo",
        data={"repo_id": repo.id},
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    # Should show the repo as assigned (with Remove button)
    assert "Remove" in resp.text
    assert "myrepo" in resp.text

    # Verify worktree exists
    wt_path = tmp_path / "worktrees" / ticket.id / "myrepo"
    assert wt_path.exists()


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_htmx_unassign_repo_with_confirm(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
    git_manager: GitManager,
    tmp_path: Path,
) -> None:
    """HTMX unassign-repo removes repo assignment."""
    source = _init_test_repo(tmp_path / "source")
    repo = git_manager.clone_repo(f"file://{source}", name="myrepo")

    user = auth.create_user("alice", "pass", is_admin=False)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    # Assign first
    await client.post(
        f"/htmx/tickets/{ticket.id}/assign-repo",
        data={"repo_id": repo.id},
        headers={"Cookie": f"token={user.token}"},
    )

    # Unassign
    resp = await client.post(
        f"/htmx/tickets/{ticket.id}/unassign-repo",
        data={"repo_id": repo.id},
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    # Should show the assign button again
    assert "+ myrepo" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_diff_page_renders(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
    git_manager: GitManager,
    tmp_path: Path,
) -> None:
    """GET /ticket/{id}/diff shows diff page with assigned repos."""
    source = _init_test_repo(tmp_path / "source")
    repo = git_manager.clone_repo(f"file://{source}", name="myrepo")

    user = auth.create_user("alice", "pass", is_admin=False)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    # Assign repo
    state = state_manager.load()
    state.tickets[ticket.id].repos.append(repo.id)
    state_manager.save(state)
    git_manager.create_worktree(repo.id, ticket.id, ticket.title)

    resp = await client.get(
        f"/ticket/{ticket.id}/diff",
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    assert "myrepo" in resp.text
    assert "diff2html" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_diff_page_no_repos(
    client: AsyncClient,
    auth: AuthManager,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """Diff page shows message when no repos assigned."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test ticket", "desc")

    resp = await client.get(
        f"/ticket/{ticket.id}/diff",
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    assert "No repos assigned" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_diff_page_requires_auth(
    client: AsyncClient,
    state_manager: StateManager,
    config: KannixConfig,
) -> None:
    """Diff page redirects to login when unauthenticated."""
    ticket_mgr = TicketManager(state_manager, config)
    ticket = ticket_mgr.create("Test", "desc")
    resp = await client.get(f"/ticket/{ticket.id}/diff", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_htmx_clone_repo(
    client: AsyncClient,
    auth: AuthManager,
    tmp_path: Path,
) -> None:
    """HTMX clone repo form works."""
    source = _init_test_repo(tmp_path / "source")
    user = auth.create_user("alice", "pass", is_admin=False)

    resp = await client.post(
        "/htmx/repos/clone",
        data={"url": f"file://{source}", "name": "cloned"},
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    assert "cloned" in resp.text


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
async def test_htmx_delete_repo(
    client: AsyncClient,
    auth: AuthManager,
    git_manager: GitManager,
    tmp_path: Path,
) -> None:
    """HTMX delete repo removes it."""
    source = _init_test_repo(tmp_path / "source")
    repo = git_manager.clone_repo(f"file://{source}", name="todelete")

    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.delete(
        f"/htmx/repos/{repo.id}",
        headers={"Cookie": f"token={user.token}"},
    )
    assert resp.status_code == 200
    assert resp.text == ""

    # Verify gone
    assert git_manager.get_repo(repo.id) is None
