"""Tests for .pi backup during archive and delete."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kannix.config import load_config
from kannix.git import GitManager
from kannix.state import StateManager
from kannix.tickets import TicketManager


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create temporary directories for repos, worktrees, and archives."""
    dirs = {
        "repos": tmp_path / "repos",
        "worktrees": tmp_path / "worktrees",
        "archives": tmp_path / "archives",
    }
    for d in dirs.values():
        d.mkdir()
    return dirs


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def config(tmp_path: Path, tmp_dirs: dict[str, Path]) -> object:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(
        json.dumps(
            {
                "columns": ["Backlog", "In Progress", "Done"],
                "repos_dir": str(tmp_dirs["repos"]),
                "worktree_dir": str(tmp_dirs["worktrees"]),
                "archive_dir": str(tmp_dirs["archives"]),
            }
        )
    )
    return load_config(config_path)


@pytest.fixture
def git_manager(tmp_dirs: dict[str, Path], state_manager: StateManager) -> GitManager:
    return GitManager(
        repos_dir=tmp_dirs["repos"],
        worktree_dir=tmp_dirs["worktrees"],
        state_manager=state_manager,
    )


@pytest.fixture
def tickets(state_manager: StateManager, config: object, git_manager: GitManager) -> TicketManager:
    return TicketManager(state_manager, config, git_manager=git_manager)


def _create_fake_pi(worktrees_dir: Path, dir_name: str) -> Path:
    """Create a fake .pi directory in a ticket workspace."""
    ws = worktrees_dir / dir_name
    pi = ws / ".pi"
    pi.mkdir(parents=True)
    (pi / "plans").mkdir()
    (pi / "plans" / "plan1.md").write_text("# Test Plan\n- step 1\n- step 2")
    (pi / "session.json").write_text('{"model": "test"}')
    return pi


def test_archive_backs_up_pi(tickets: TicketManager, tmp_dirs: dict[str, Path]):
    ticket = tickets.create("Test backup", "some desc")
    # Create a fake .pi directory in the worktree location
    _create_fake_pi(tmp_dirs["worktrees"], ticket.dir_name)

    archived = tickets.archive(ticket.id)
    assert archived is not None
    assert archived.archived is True

    # Check that archive directory was created
    archive_entries = list(tmp_dirs["archives"].iterdir())
    assert len(archive_entries) == 1
    archive_dir = archive_entries[0]
    assert ticket.dir_name in archive_dir.name

    # Check .pi was copied
    pi_backup = archive_dir / ".pi"
    assert pi_backup.exists()
    assert (pi_backup / "plans" / "plan1.md").exists()
    assert (pi_backup / "session.json").exists()


def test_delete_backs_up_pi(tickets: TicketManager, tmp_dirs: dict[str, Path]):
    ticket = tickets.create("Delete with backup", "desc")
    _create_fake_pi(tmp_dirs["worktrees"], ticket.dir_name)

    assert tickets.delete(ticket.id) is True

    # Ticket is gone
    assert tickets.get(ticket.id) is None

    # But .pi was backed up
    archive_entries = list(tmp_dirs["archives"].iterdir())
    assert len(archive_entries) == 1
    pi_backup = archive_entries[0] / ".pi"
    assert pi_backup.exists()
    assert (pi_backup / "plans" / "plan1.md").exists()


def test_archive_without_pi_dir(tickets: TicketManager, tmp_dirs: dict[str, Path]):
    """Archive works even if there's no .pi directory to backup."""
    ticket = tickets.create("No pi", "")
    archived = tickets.archive(ticket.id)
    assert archived is not None
    assert archived.archived is True
    # No archive created since there was no .pi
    archive_entries = list(tmp_dirs["archives"].iterdir())
    assert len(archive_entries) == 0


def test_archive_without_git_manager(state_manager: StateManager, tmp_dirs: dict[str, Path]):
    """Archive works without git manager (no backup, just marks archived)."""
    from kannix.config import load_config

    config_path = tmp_dirs["worktrees"].parent / "kannix2.json"
    config_path.write_text(json.dumps({"columns": ["Backlog", "Done"]}))
    config = load_config(config_path)

    mgr = TicketManager(state_manager, config)
    ticket = mgr.create("No git", "")
    archived = mgr.archive(ticket.id)
    assert archived is not None
    assert archived.archived is True
