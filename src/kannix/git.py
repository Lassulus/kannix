"""Git repository and worktree management."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import uuid
from typing import TYPE_CHECKING

from kannix.state import RepoState

if TYPE_CHECKING:
    from pathlib import Path

    from kannix.state import StateManager

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a git-branch-safe slug."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s


def ticket_dir_name(ticket_id: str, title: str) -> str:
    """Generate a human-friendly directory name for a ticket workspace.

    Format: <slugified-title>-<short-id>, e.g. "fix-auth-bug-a3f8b2c1"
    """
    short_id = ticket_id[:8]
    slug = _slugify(title)
    if slug:
        return f"{slug}-{short_id}"
    return short_id


def _run_git(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command."""
    cmd = ["git", *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _detect_default_branch(repo_path: Path) -> str:
    """Detect the default branch of a bare repo."""
    result = _run_git("symbolic-ref", "HEAD", cwd=repo_path, check=False)
    if result.returncode == 0:
        ref = result.stdout.strip()
        # refs/heads/main -> main
        return ref.split("/")[-1]
    return "main"


class GitManager:
    """Manages git repositories and worktrees for tickets."""

    def __init__(
        self,
        repos_dir: Path,
        worktree_dir: Path,
        state_manager: StateManager,
    ) -> None:
        self._repos_dir = repos_dir
        self._worktree_dir = worktree_dir
        self._state_manager = state_manager

    def clone_repo(self, url: str, name: str | None = None) -> RepoState:
        """Clone a git repo as a bare repo.

        Args:
            url: Git clone URL.
            name: Optional repo name. Derived from URL if not given.

        Returns:
            The created RepoState.
        """
        if name is None:
            # Derive name from URL: https://example.com/foo/bar.git -> bar
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]

        dest = self._repos_dir / f"{name}.git"
        _run_git("clone", "--bare", url, str(dest))
        # Bare clones don't track remote branches by default — fix that
        _run_git(
            "-C",
            str(dest),
            "config",
            "remote.origin.fetch",
            "+refs/heads/*:refs/remotes/origin/*",
        )

        default_branch = _detect_default_branch(dest)

        repo = RepoState(
            id=uuid.uuid4().hex[:16],
            name=name,
            url=url,
            path=str(dest),
            default_branch=default_branch,
        )

        state = self._state_manager.load()
        state.repos[repo.id] = repo
        self._state_manager.save(state)

        return repo

    def list_repos(self) -> list[RepoState]:
        """List all registered repos."""
        state = self._state_manager.load()
        return list(state.repos.values())

    def get_repo(self, repo_id: str) -> RepoState | None:
        """Get a repo by ID."""
        state = self._state_manager.load()
        return state.repos.get(repo_id)

    def delete_repo(self, repo_id: str) -> bool:
        """Delete a repo from state and disk."""
        state = self._state_manager.load()
        repo = state.repos.pop(repo_id, None)
        if repo is None:
            return False
        self._state_manager.save(state)

        repo_path = self._repos_dir / f"{repo.name}.git"
        if repo_path.exists():
            shutil.rmtree(repo_path)

        return True

    def _branch_name(self, ticket_id: str, title: str) -> str:
        """Generate branch name for a ticket."""
        short_id = ticket_id[:8]
        slug = _slugify(title)
        if slug:
            return f"ticket/{short_id}-{slug}"
        return f"ticket/{short_id}"

    def _ticket_dir(self, ticket_id: str) -> str:
        """Get the ticket workspace directory name from state."""
        state = self._state_manager.load()
        ticket = state.tickets.get(ticket_id)
        title = ticket.title if ticket else ""
        return ticket_dir_name(ticket_id, title)

    def _worktree_path(self, ticket_id: str, repo_name: str) -> Path:
        """Get the worktree path for a ticket+repo."""
        return self._worktree_dir / self._ticket_dir(ticket_id) / repo_name

    def create_worktree(self, repo_id: str, ticket_id: str, title: str) -> Path:
        """Create a worktree for a ticket in a repo.

        Creates a new branch from the default branch HEAD.

        Returns:
            Path to the worktree directory.

        Raises:
            ValueError: If repo not found.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            raise ValueError(f"Repo not found: {repo_id}")

        branch = self._branch_name(ticket_id, title)
        wt_path = self._worktree_path(ticket_id, repo.name)
        wt_path.parent.mkdir(parents=True, exist_ok=True)

        repo_path = self._repos_dir / f"{repo.name}.git"

        # Check if branch already exists (re-assignment)
        branch_check = _run_git(
            "show-ref",
            "--verify",
            f"refs/heads/{branch}",
            cwd=repo_path,
            check=False,
        )
        if branch_check.returncode == 0:
            # Branch exists, reuse it
            _run_git(
                "worktree",
                "add",
                str(wt_path),
                branch,
                cwd=repo_path,
            )
        else:
            # Create worktree with new branch from default branch
            _run_git(
                "worktree",
                "add",
                "-b",
                branch,
                str(wt_path),
                repo.default_branch,
                cwd=repo_path,
            )

        # Set user config in worktree for commits
        _run_git("config", "user.email", "kannix@localhost", cwd=wt_path)
        _run_git("config", "user.name", "Kannix", cwd=wt_path)

        return wt_path

    def delete_worktree(self, repo_id: str, ticket_id: str) -> bool:
        """Delete a worktree for a ticket.

        Returns:
            True if deleted, False if not found.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return False

        wt_path = self._worktree_path(ticket_id, repo.name)
        if not wt_path.exists():
            return False

        repo_path = self._repos_dir / f"{repo.name}.git"

        # Remove worktree via git
        _run_git(
            "worktree",
            "remove",
            "--force",
            str(wt_path),
            cwd=repo_path,
            check=False,
        )

        # Clean up if git didn't remove it
        if wt_path.exists():
            shutil.rmtree(wt_path)

        return True

    def get_worktree_path(self, repo_id: str, ticket_id: str) -> Path | None:
        """Get the worktree path for a ticket+repo, or None."""
        repo = self.get_repo(repo_id)
        if repo is None:
            return None
        wt_path = self._worktree_path(ticket_id, repo.name)
        if wt_path.exists():
            return wt_path
        return None

    def get_diff(self, repo_id: str, ticket_id: str) -> str:
        """Get the diff for a ticket's worktree vs merge-base.

        Returns unified diff string, or empty string if no changes.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return ""

        wt_path = self._worktree_path(ticket_id, repo.name)
        if not wt_path.exists():
            return ""

        # Find merge-base with default branch
        merge_base_result = _run_git(
            "merge-base",
            "HEAD",
            repo.default_branch,
            cwd=wt_path,
            check=False,
        )
        if merge_base_result.returncode != 0:
            return ""

        merge_base = merge_base_result.stdout.strip()

        # Get diff from merge-base to HEAD
        diff_result = _run_git(
            "diff",
            merge_base,
            "HEAD",
            cwd=wt_path,
            check=False,
        )
        return diff_result.stdout
