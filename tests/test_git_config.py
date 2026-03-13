"""Tests for git repo config and state models."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from kannix.config import load_config
from kannix.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


def test_config_repos_dir_default(tmp_path: Path) -> None:
    """repos_dir defaults to None when not specified."""
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo"]}))
    config = load_config(config_path)
    assert config.repos_dir is None


def test_config_worktree_dir_default(tmp_path: Path) -> None:
    """worktree_dir defaults to None when not specified."""
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo"]}))
    config = load_config(config_path)
    assert config.worktree_dir is None


def test_config_repos_dir_set(tmp_path: Path) -> None:
    """repos_dir can be set via config."""
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo"], "repos_dir": "/tmp/repos"}))
    config = load_config(config_path)
    assert config.repos_dir == "/tmp/repos"


def test_config_worktree_dir_set(tmp_path: Path) -> None:
    """worktree_dir can be set via config."""
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo"], "worktree_dir": "/tmp/wt"}))
    config = load_config(config_path)
    assert config.worktree_dir == "/tmp/wt"


def test_state_repos_empty_default(tmp_path: Path) -> None:
    """State repos dict defaults to empty."""
    sm = StateManager(tmp_path / "state.json")
    state = sm.load()
    assert state.repos == {}


def test_state_repo_round_trip(tmp_path: Path) -> None:
    """RepoState can be saved and loaded."""
    from kannix.state import RepoState

    sm = StateManager(tmp_path / "state.json")
    state = sm.load()
    state.repos["repo1"] = RepoState(
        id="repo1",
        name="myrepo",
        url="https://github.com/test/repo.git",
        path="/tmp/repos/myrepo",
        default_branch="main",
    )
    sm.save(state)

    loaded = sm.load()
    assert "repo1" in loaded.repos
    repo = loaded.repos["repo1"]
    assert repo.id == "repo1"
    assert repo.name == "myrepo"
    assert repo.url == "https://github.com/test/repo.git"
    assert repo.path == "/tmp/repos/myrepo"
    assert repo.default_branch == "main"


def test_state_ticket_repos_default_empty(tmp_path: Path) -> None:
    """Ticket repos list defaults to empty."""
    from kannix.state import TicketState

    ticket = TicketState(
        id="t1",
        title="test",
        description="",
        column="Todo",
        assigned_to=None,
    )
    assert ticket.repos == []


def test_state_ticket_repos_round_trip(tmp_path: Path) -> None:
    """Ticket repos list persists through save/load."""
    from kannix.state import TicketState

    sm = StateManager(tmp_path / "state.json")
    state = sm.load()
    state.tickets["t1"] = TicketState(
        id="t1",
        title="test",
        description="",
        column="Todo",
        assigned_to=None,
        repos=["repo1", "repo2"],
    )
    sm.save(state)

    loaded = sm.load()
    assert loaded.tickets["t1"].repos == ["repo1", "repo2"]
