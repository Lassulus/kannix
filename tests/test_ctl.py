"""Tests for kannix-ctl CLI tool."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from kannix.app import create_app
from kannix.auth import AuthManager
from kannix.ctl import main as ctl_main
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


# --- API endpoint tests ---


async def test_list_columns_endpoint(client: AsyncClient, auth: AuthManager) -> None:
    """GET /api/columns returns configured columns."""
    user = auth.create_user("alice", "pass", is_admin=False)
    resp = await client.get(
        "/api/columns",
        headers={"Authorization": f"Bearer {user.token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == ["Backlog", "In Progress", "Done"]


async def test_list_columns_requires_auth(client: AsyncClient) -> None:
    """GET /api/columns requires authentication."""
    resp = await client.get("/api/columns")
    assert resp.status_code == 401


# --- CLI unit tests (mocking HTTP) ---


def test_ctl_get_shows_ticket(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl get prints ticket info as JSON."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("My Task", "Task description")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "get"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                {
                    "id": ticket.id,
                    "title": "My Task",
                    "description": "Task description",
                    "column": "Backlog",
                    "assigned_to": None,
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["title"] == "My Task"
        assert data["description"] == "Task description"
        assert data["column"] == "Backlog"


def test_ctl_set_title(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl set --description updates the description."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("My Task", "old desc")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "set", "--description", "new desc"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                {
                    "id": ticket.id,
                    "title": "My Task",
                    "description": "new desc",
                    "column": "Backlog",
                    "assigned_to": None,
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "My Task" in out


def test_ctl_set_description(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl set --description updates description."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("Task", "old desc")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "set", "--description", "new desc"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                {
                    "id": ticket.id,
                    "title": "Task",
                    "description": "new desc",
                    "column": "Backlog",
                    "assigned_to": None,
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "new desc" in out


def test_ctl_move(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl move <column> moves the ticket."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("Task", "")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "move", "In Progress"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                {
                    "id": ticket.id,
                    "title": "Task",
                    "description": "",
                    "column": "In Progress",
                    "assigned_to": None,
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "In Progress" in out


def test_ctl_list_columns(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl list-columns prints available columns."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "list-columns"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(["Backlog", "In Progress", "Done"]),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "Backlog" in out
        assert "In Progress" in out
        assert "Done" in out


def test_ctl_list_tickets(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl list-tickets prints all tickets."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "list-tickets"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                [
                    {
                        "id": "abc",
                        "title": "Task 1",
                        "description": "",
                        "column": "Backlog",
                        "assigned_to": None,
                    },
                    {
                        "id": "def",
                        "title": "Task 2",
                        "description": "",
                        "column": "Done",
                        "assigned_to": None,
                    },
                ]
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "Task 1" in out
        assert "Task 2" in out


def test_ctl_list_repos(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl list-repos prints all repos."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "list-repos"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            200,
            json.dumps(
                [
                    {
                        "id": "repo1",
                        "name": "myrepo",
                        "url": "https://example.com/repo.git",
                        "path": "/tmp/repos/myrepo.git",
                        "default_branch": "main",
                    },
                ]
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "myrepo" in out
        assert "main" in out


def test_ctl_assign_repo(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl assign-repo assigns a repo to current ticket."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("Task", "desc")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "assign-repo", "repo123"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (200, json.dumps({"status": "assigned"}))
        ctl_main()
        out = capsys.readouterr().out
        assert "assigned" in out
        # Verify the HTTP call
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert "/api/repos/assign" in call_args[0][0]


def test_ctl_unassign_repo(
    auth: AuthManager,
    ticket_mgr: TicketManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl unassign-repo removes a repo from current ticket."""
    user = auth.create_user("alice", "pass", is_admin=False)
    ticket = ticket_mgr.create("Task", "desc")

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": ticket.id,
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "unassign-repo", "repo123"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (200, json.dumps({"status": "unassigned"}))
        ctl_main()
        out = capsys.readouterr().out
        assert "unassigned" in out


def test_ctl_worktrees(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl worktrees shows worktree env vars."""
    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": "tok",
        "KANNIX_TICKET_ID": "tid",
        "KANNIX_WORKTREE_MYREPO": "/tmp/wt/myrepo",
        "KANNIX_WORKTREE_OTHER": "/tmp/wt/other",
    }
    with (
        patch.dict("os.environ", env, clear=False),
        patch("sys.argv", ["kannix-ctl", "worktrees"]),
    ):
        ctl_main()
        out = capsys.readouterr().out
        assert "myrepo" in out
        assert "/tmp/wt/myrepo" in out
        assert "other" in out


def test_ctl_worktrees_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl worktrees shows message when no worktrees."""
    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": "tok",
        "KANNIX_TICKET_ID": "tid",
    }
    # Clear any existing KANNIX_WORKTREE_ vars
    clean_env = {k: v for k, v in env.items()}
    with (
        patch.dict("os.environ", clean_env, clear=True),
        patch("sys.argv", ["kannix-ctl", "worktrees"]),
    ):
        ctl_main()
        err = capsys.readouterr().err
        assert "No worktrees" in err


def test_ctl_clone_repo(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl clone-repo clones a repo by URL."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "clone-repo", "https://example.com/repo.git"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            201,
            json.dumps(
                {
                    "id": "abc123",
                    "name": "repo",
                    "url": "https://example.com/repo.git",
                    "path": "/tmp/repos/repo.git",
                    "default_branch": "main",
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "repo" in out
        assert "main" in out
        # Verify the HTTP call
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert "/api/repos" in call_args[0][0]
        assert call_args[1]["method"] == "POST"


def test_ctl_clone_repo_with_name(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl clone-repo --name sets custom name."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch(
            "sys.argv",
            ["kannix-ctl", "clone-repo", "https://example.com/repo.git", "--name", "myrepo"],
        ),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (
            201,
            json.dumps(
                {
                    "id": "abc123",
                    "name": "myrepo",
                    "url": "https://example.com/repo.git",
                    "path": "/tmp/repos/myrepo.git",
                    "default_branch": "main",
                }
            ),
        )
        ctl_main()
        out = capsys.readouterr().out
        assert "myrepo" in out
        # Verify name was sent
        call_data = mock_req.call_args[1]["data"]
        assert call_data["name"] == "myrepo"


def test_ctl_delete_repo(
    auth: AuthManager,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl delete-repo deletes a repo."""
    user = auth.create_user("alice", "pass", is_admin=False)

    env = {
        "KANNIX_URL": "http://test",
        "KANNIX_TOKEN": user.token,
        "KANNIX_TICKET_ID": "dummy",
    }
    with (
        patch.dict("os.environ", env),
        patch("sys.argv", ["kannix-ctl", "delete-repo", "abc123"]),
        patch("kannix.ctl._http_request") as mock_req,
    ):
        mock_req.return_value = (200, json.dumps({"status": "deleted"}))
        ctl_main()
        out = capsys.readouterr().out
        assert "deleted" in out.lower() or "Deleted" in out


def test_ctl_missing_env_vars(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """kannix-ctl exits with error when env vars are missing."""
    env = {"KANNIX_URL": "", "KANNIX_TOKEN": "", "KANNIX_TICKET_ID": ""}
    with (
        patch.dict("os.environ", env, clear=False),
        patch("sys.argv", ["kannix-ctl", "get"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        ctl_main()
    assert exc_info.value.code != 0


# --- tmux env var tests ---


def test_tmux_create_session_sets_env_vars() -> None:
    """TmuxManager.create_session should set KANNIX_* env vars."""
    from kannix.tmux import TmuxManager

    mgr = TmuxManager(socket_name="kannix-test-env")
    try:
        mgr.create_session(
            "test-env-sess",
            env={
                "KANNIX_URL": "http://localhost:9876",
                "KANNIX_TOKEN": "testtoken123",
                "KANNIX_TICKET_ID": "test-env-sess",
            },
        )
        assert mgr.session_exists("test-env-sess")
        # Check env var is set in tmux session
        result = subprocess.run(
            [
                "tmux",
                "-L",
                "kannix-test-env",
                "show-environment",
                "-t",
                "test-env-sess",
                "KANNIX_URL",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert "http://localhost:9876" in result.stdout
    finally:
        mgr.kill_session("test-env-sess")
        subprocess.run(
            ["tmux", "-L", "kannix-test-env", "kill-server"],
            capture_output=True,
            check=False,
        )
