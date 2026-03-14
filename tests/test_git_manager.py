"""Tests for GitManager — clone, worktree, diff."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from kannix.git import GitManager
from kannix.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


def _is_sandbox() -> bool:
    return bool(os.environ.get("NIX_BUILD_TOP"))


def _init_test_repo(path: Path) -> Path:
    """Create a bare git repo with one commit for testing."""
    work = path / "work"
    work.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-b", "main", str(work)],
        capture_output=True,
        check=True,
    )
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
    (work / "README.md").write_text("# Test repo\n")
    subprocess.run(["git", "-C", str(work), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "init"],
        capture_output=True,
        check=True,
    )
    # Create bare clone
    bare = path / "bare.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)],
        capture_output=True,
        check=True,
    )
    return bare


@pytest.fixture
def git_env(tmp_path: Path) -> tuple[GitManager, StateManager, Path]:
    """Set up GitManager with temp dirs."""
    repos_dir = tmp_path / "repos"
    worktree_dir = tmp_path / "worktrees"
    repos_dir.mkdir()
    worktree_dir.mkdir()
    sm = StateManager(tmp_path / "state.json")
    gm = GitManager(
        repos_dir=repos_dir,
        worktree_dir=worktree_dir,
        state_manager=sm,
    )
    return gm, sm, tmp_path


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_clone_repo(git_env: tuple[GitManager, StateManager, Path]) -> None:
    """clone_repo creates a bare clone and registers it in state."""
    gm, sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")

    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    assert repo.name == "myrepo"
    assert repo.default_branch == "main"
    assert (gm._repos_dir / "myrepo.git").exists()

    # Verify in state
    state = sm.load()
    assert repo.id in state.repos


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_clone_repo_auto_name(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """clone_repo derives name from URL when not specified."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")

    repo = gm.clone_repo(f"file://{source}")
    assert repo.name == "bare"


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_list_repos(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """list_repos returns all registered repos."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    gm.clone_repo(f"file://{source}", name="repo1")

    source2 = _init_test_repo(tmp_path / "source2")
    gm.clone_repo(f"file://{source2}", name="repo2")

    repos = gm.list_repos()
    names = {r.name for r in repos}
    assert names == {"repo1", "repo2"}


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_delete_repo(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """delete_repo removes from state and disk."""
    gm, sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="todelete")
    repo_path = gm._repos_dir / "todelete.git"
    assert repo_path.exists()

    gm.delete_repo(repo.id)
    assert not repo_path.exists()
    state = sm.load()
    assert repo.id not in state.repos


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_create_worktree(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """create_worktree creates a worktree with a ticket branch."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")

    wt_path = gm.create_worktree(repo.id, "ticket123", "Fix the bug")
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    # Check branch name
    result = subprocess.run(
        ["git", "-C", str(wt_path), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    branch = result.stdout.strip()
    assert branch.startswith("ticket/")
    assert "ticket12" in branch  # short id
    assert "fix-the-bug" in branch


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_delete_worktree(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """delete_worktree removes the worktree."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")

    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")
    assert wt_path.exists()

    gm.delete_worktree(repo.id, "ticket123")
    assert not wt_path.exists()


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_empty(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff returns empty string when no changes."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    gm.create_worktree(repo.id, "ticket123", "Test")

    diff = gm.get_diff(repo.id, "ticket123")
    assert diff == ""


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_with_changes(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff returns unified diff when there are changes."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Make a change and commit
    (wt_path / "new_file.txt").write_text("hello\n")
    subprocess.run(
        ["git", "-C", str(wt_path), "add", "."],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "add file"],
        capture_output=True,
        check=True,
    )

    diff = gm.get_diff(repo.id, "ticket123")
    assert "new_file.txt" in diff
    assert "+hello" in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_unstaged_changes(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff includes unstaged modifications to tracked files."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Modify a tracked file without staging or committing
    (wt_path / "README.md").write_text("# Modified\n")

    diff = gm.get_diff(repo.id, "ticket123")
    assert "README.md" in diff
    assert "+# Modified" in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_untracked_files(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff includes untracked (new) files."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Create a new file without staging
    (wt_path / "brand_new.txt").write_text("I am new\n")

    diff = gm.get_diff(repo.id, "ticket123")
    assert "brand_new.txt" in diff
    assert "+I am new" in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_mixed_committed_and_unstaged(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff shows committed changes, unstaged edits, and untracked files together."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Committed change
    (wt_path / "committed.txt").write_text("committed\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "add committed"],
        capture_output=True,
        check=True,
    )

    # Unstaged edit to tracked file
    (wt_path / "README.md").write_text("# Edited\n")

    # Untracked new file
    (wt_path / "untracked.txt").write_text("untracked\n")

    diff = gm.get_diff(repo.id, "ticket123")
    assert "committed.txt" in diff
    assert "+committed" in diff
    assert "README.md" in diff
    assert "+# Edited" in diff
    assert "untracked.txt" in diff
    assert "+untracked" in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_worktree_path(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_worktree_path returns the correct path."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    gm.create_worktree(repo.id, "ticket123", "Test")

    path = gm.get_worktree_path(repo.id, "ticket123")
    assert path is not None
    assert path.exists()


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_reassign_worktree_reuses_branch(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """Re-creating a worktree after deletion reuses the existing branch."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")

    # Create, make a commit, delete, re-create
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")
    (wt_path / "new.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "change"],
        capture_output=True,
        check=True,
    )
    gm.delete_worktree(repo.id, "ticket123")
    assert not wt_path.exists()

    # Re-create — should succeed and retain the commit
    wt_path2 = gm.create_worktree(repo.id, "ticket123", "Test")
    assert wt_path2.exists()
    assert (wt_path2 / "new.txt").exists()  # commit preserved


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_against_upstream(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff compares against origin/<default_branch>, not a local branch."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Make a change and commit on the ticket branch
    (wt_path / "new_file.txt").write_text("hello\n")
    subprocess.run(
        ["git", "-C", str(wt_path), "add", "."],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "add file"],
        capture_output=True,
        check=True,
    )

    diff = gm.get_diff(repo.id, "ticket123")
    assert "new_file.txt" in diff

    # Push a new commit to the upstream (source bare repo) — the diff
    # should still work and only show our ticket's changes
    upstream_work = tmp_path / "upstream_work"
    upstream_work.mkdir()
    subprocess.run(
        ["git", "clone", f"file://{source}", str(upstream_work)],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "config", "user.email", "t@t.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "config", "user.name", "T"],
        capture_output=True,
        check=True,
    )
    (upstream_work / "upstream_change.txt").write_text("upstream\n")
    subprocess.run(
        ["git", "-C", str(upstream_work), "add", "."],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "commit", "-m", "upstream change"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "push"],
        capture_output=True,
        check=True,
    )

    # After fetching, diff should still show only our change
    gm.fetch_repo(repo.id)
    diff = gm.get_diff(repo.id, "ticket123")
    assert "new_file.txt" in diff
    # Should NOT include the upstream change in the diff
    assert "upstream_change.txt" not in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_fetch_repo(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """fetch_repo fetches latest changes from upstream."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")

    # Push a new commit to upstream
    upstream_work = tmp_path / "upstream_work"
    subprocess.run(
        ["git", "clone", f"file://{source}", str(upstream_work)],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "config", "user.email", "t@t.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "config", "user.name", "T"],
        capture_output=True,
        check=True,
    )
    (upstream_work / "new.txt").write_text("new\n")
    subprocess.run(
        ["git", "-C", str(upstream_work), "add", "."],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "commit", "-m", "new commit"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_work), "push"],
        capture_output=True,
        check=True,
    )

    # Fetch and verify origin/main is updated
    assert gm.fetch_repo(repo.id) is True

    repo_path = gm._repos_dir / "myrepo.git"
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--oneline", "origin/main"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "new commit" in result.stdout


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_fetch_repo_not_found(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """fetch_repo returns False for unknown repo."""
    gm, _sm, _tmp_path = git_env
    assert gm.fetch_repo("nonexistent") is False


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_commits_empty(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_commits returns empty list when no changes."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    gm.create_worktree(repo.id, "ticket123", "Test")

    commits = gm.get_commits(repo.id, "ticket123")
    assert commits == []


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_commits_with_changes(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_commits returns commits in chronological order with diffs."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Make two commits
    (wt_path / "file1.txt").write_text("first\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "add file1"],
        capture_output=True,
        check=True,
    )

    (wt_path / "file2.txt").write_text("second\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "add file2"],
        capture_output=True,
        check=True,
    )

    commits = gm.get_commits(repo.id, "ticket123")
    assert len(commits) == 2

    # Chronological order — oldest first
    assert commits[0].message == "add file1"
    assert commits[1].message == "add file2"

    # Each commit has its own diff
    assert "file1.txt" in commits[0].diff
    assert "file2.txt" not in commits[0].diff
    assert "file2.txt" in commits[1].diff
    assert "file1.txt" not in commits[1].diff

    # Commits have metadata
    assert len(commits[0].sha) == 40
    assert commits[0].author != ""
    assert commits[0].date != ""


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_diff_includes_uncommitted(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_diff includes staged changes and modifications to tracked files."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Staged new file
    (wt_path / "staged.txt").write_text("staged\n")
    subprocess.run(
        ["git", "-C", str(wt_path), "add", "staged.txt"],
        capture_output=True,
        check=True,
    )

    # Unstaged modification to a tracked file
    (wt_path / "README.md").write_text("modified\n")

    diff = gm.get_diff(repo.id, "ticket123")
    assert "staged.txt" in diff
    assert "README.md" in diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_commits_includes_uncommitted(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_commits appends uncommitted changes as a synthetic entry."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    # Make a committed change
    (wt_path / "committed.txt").write_text("committed\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "first commit"],
        capture_output=True,
        check=True,
    )

    # Make uncommitted changes: staged new file + unstaged edit to tracked file
    (wt_path / "staged.txt").write_text("staged\n")
    subprocess.run(
        ["git", "-C", str(wt_path), "add", "staged.txt"],
        capture_output=True,
        check=True,
    )
    (wt_path / "committed.txt").write_text("modified\n")

    commits = gm.get_commits(repo.id, "ticket123")
    assert len(commits) == 2

    # First is the real commit
    assert commits[0].message == "first commit"
    assert "committed.txt" in commits[0].diff

    # Second is the synthetic uncommitted entry
    assert commits[1].sha == "working-tree"
    assert commits[1].message == "Uncommitted changes"
    assert "staged.txt" in commits[1].diff
    assert "committed.txt" in commits[1].diff


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_get_commits_no_uncommitted_entry_when_clean(
    git_env: tuple[GitManager, StateManager, Path],
) -> None:
    """get_commits does not add working-tree entry when worktree is clean."""
    gm, _sm, tmp_path = git_env
    source = _init_test_repo(tmp_path / "source")
    repo = gm.clone_repo(f"file://{source}", name="myrepo")
    wt_path = gm.create_worktree(repo.id, "ticket123", "Test")

    (wt_path / "file.txt").write_text("change\n")
    subprocess.run(["git", "-C", str(wt_path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "commit", "-m", "clean commit"],
        capture_output=True,
        check=True,
    )

    commits = gm.get_commits(repo.id, "ticket123")
    assert len(commits) == 1
    assert commits[0].sha != "working-tree"


@pytest.mark.skipif(_is_sandbox(), reason="git tests skipped in nix sandbox")
def test_slugify_title() -> None:
    """Branch names are properly slugified."""
    from kannix.git import _slugify

    assert _slugify("Fix the Bug!") == "fix-the-bug"
    assert _slugify("  spaces  ") == "spaces"
    assert _slugify("UPPER/case") == "upper-case"
    assert _slugify("a--b--c") == "a-b-c"
