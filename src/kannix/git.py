"""Git repository and worktree management."""

from __future__ import annotations

import datetime
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
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


@dataclass
class CommitInfo:
    """Information about a single commit."""

    sha: str
    author: str
    date: str
    message: str
    diff: str


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
        # Fetch remote tracking branches now that refspec is configured
        _run_git("fetch", "origin", cwd=dest, check=False)

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
        if ticket and ticket.dir_name:
            return ticket.dir_name
        return ticket_id

    def _worktree_path(self, ticket_id: str, repo_name: str) -> Path:
        """Get the worktree path for a ticket+repo."""
        return self._worktree_dir / self._ticket_dir(ticket_id) / repo_name

    def fetch_repo(self, repo_id: str) -> bool:
        """Fetch latest changes from upstream for a repo.

        Returns:
            True if fetch succeeded, False if repo not found or fetch failed.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return False

        repo_path = self._repos_dir / f"{repo.name}.git"
        result = _run_git("fetch", "origin", cwd=repo_path, check=False)
        return result.returncode == 0

    def get_upstream_ref(self, repo_id: str) -> str | None:
        """Get the upstream ref name for a repo (e.g. 'origin/main').

        Returns None if repo not found.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return None
        return f"origin/{repo.default_branch}"

    def create_worktree(self, repo_id: str, ticket_id: str, title: str) -> Path:
        """Create a worktree for a ticket in a repo.

        Creates a new branch from the upstream default branch HEAD.

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

        # Fetch latest upstream before creating worktree
        _run_git("fetch", "origin", cwd=repo_path, check=False)

        upstream_ref = f"origin/{repo.default_branch}"

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
            # Create worktree with new branch from upstream default branch
            _run_git(
                "worktree",
                "add",
                "-b",
                branch,
                str(wt_path),
                upstream_ref,
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

    def get_ticket_workspace_path(self, ticket_id: str) -> Path | None:
        """Get the ticket workspace directory (parent of repo worktrees).

        Returns None if the directory doesn't exist.
        """
        ticket_dir = self._ticket_dir(ticket_id)
        ws_path = self._worktree_dir / ticket_dir
        if ws_path.exists():
            return ws_path
        return None

    def backup_ticket_pi(self, ticket_id: str, archive_dir: Path) -> Path | None:
        """Backup the .pi directory from a ticket's workspace to the archive dir.

        Returns the archive path if backup was created, None if no .pi found.
        """
        ws_path = self.get_ticket_workspace_path(ticket_id)
        if ws_path is None:
            return None

        pi_path = ws_path / ".pi"
        if not pi_path.exists():
            return None

        ticket_dir = self._ticket_dir(ticket_id)
        timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
        dest = archive_dir / f"{ticket_dir}-{timestamp}" / ".pi"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pi_path, dest)
        return dest.parent

    def delete_ticket_workspace(self, ticket_id: str) -> bool:
        """Delete all worktrees for a ticket and remove the workspace directory.

        Returns True if anything was cleaned up.
        """
        # Remove git worktrees for all repos
        state = self._state_manager.load()
        ticket = state.tickets.get(ticket_id)
        if ticket is None:
            return False

        for repo_id in list(ticket.repos):
            self.delete_worktree(repo_id, ticket_id)

        # Remove the entire ticket workspace directory
        ws_path = self.get_ticket_workspace_path(ticket_id)
        if ws_path is not None and ws_path.exists():
            shutil.rmtree(ws_path)
            return True
        return False

    def get_diff(self, repo_id: str, ticket_id: str) -> str:
        """Get the diff for a ticket's worktree vs upstream merge-base.

        Diffs against origin/<default_branch> so the comparison is always
        against the latest upstream, not a potentially stale local branch.

        Returns unified diff string, or empty string if no changes.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return ""

        wt_path = self._worktree_path(ticket_id, repo.name)
        if not wt_path.exists():
            return ""

        upstream_ref = f"origin/{repo.default_branch}"

        # Find merge-base with upstream default branch
        merge_base_result = _run_git(
            "merge-base",
            "HEAD",
            upstream_ref,
            cwd=wt_path,
            check=False,
        )
        if merge_base_result.returncode != 0:
            return ""

        merge_base = merge_base_result.stdout.strip()

        # Get diff from merge-base to working tree (includes committed,
        # staged, and unstaged changes to tracked files)
        diff_result = _run_git(
            "diff",
            merge_base,
            cwd=wt_path,
            check=False,
        )
        parts = [diff_result.stdout]

        # Include untracked files as new-file diffs
        untracked_result = _run_git(
            "ls-files",
            "--others",
            "--exclude-standard",
            cwd=wt_path,
            check=False,
        )
        if untracked_result.returncode == 0:
            for fname in untracked_result.stdout.splitlines():
                fname = fname.strip()
                if not fname:
                    continue
                # Generate a diff for the untracked file using diff --no-index
                ut_diff = _run_git(
                    "diff",
                    "--no-index",
                    "/dev/null",
                    fname,
                    cwd=wt_path,
                    check=False,
                )
                if ut_diff.stdout:
                    # Rewrite the header so it looks like a normal a/b diff
                    patched = ut_diff.stdout.replace("/dev/null", f"a/{fname}", 1)
                    parts.append(patched)

        return "".join(parts)

    def get_commits(self, repo_id: str, ticket_id: str) -> list[CommitInfo]:
        """Get commits on a ticket branch since the upstream merge-base.

        Returns commits in chronological order (oldest first), each with
        its own diff.
        """
        repo = self.get_repo(repo_id)
        if repo is None:
            return []

        wt_path = self._worktree_path(ticket_id, repo.name)
        if not wt_path.exists():
            return []

        upstream_ref = f"origin/{repo.default_branch}"

        # Find merge-base
        merge_base_result = _run_git(
            "merge-base",
            "HEAD",
            upstream_ref,
            cwd=wt_path,
            check=False,
        )
        if merge_base_result.returncode != 0:
            return []

        merge_base = merge_base_result.stdout.strip()

        # Get commit list (oldest first) with a delimiter we can parse
        # Format: sha\x1fauthor\x1fdate\x1fmessage
        log_result = _run_git(
            "log",
            "--reverse",
            "--format=%H%x1f%an%x1f%aI%x1f%s",
            f"{merge_base}..HEAD",
            cwd=wt_path,
            check=False,
        )
        if log_result.returncode != 0 or not log_result.stdout.strip():
            return []

        commits: list[CommitInfo] = []
        for line in log_result.stdout.strip().split("\n"):
            parts = line.split("\x1f", 3)
            if len(parts) < 4:
                continue
            sha, author, date, message = parts

            # Get diff for this specific commit
            diff_result = _run_git(
                "diff",
                f"{sha}~1",
                sha,
                cwd=wt_path,
                check=False,
            )
            # For the first commit after merge-base, sha~1 might fail
            # if it's the merge-base itself; use merge-base directly
            if diff_result.returncode != 0:
                diff_result = _run_git(
                    "diff",
                    merge_base,
                    sha,
                    cwd=wt_path,
                    check=False,
                )

            commits.append(
                CommitInfo(
                    sha=sha,
                    author=author,
                    date=date,
                    message=message,
                    diff=diff_result.stdout if diff_result.returncode == 0 else "",
                )
            )

        # Check for uncommitted changes (staged + unstaged)
        uncommitted_result = _run_git(
            "diff",
            "HEAD",
            cwd=wt_path,
            check=False,
        )
        uncommitted = uncommitted_result.stdout if uncommitted_result.returncode == 0 else ""
        if uncommitted.strip():
            commits.append(
                CommitInfo(
                    sha="working-tree",
                    author="",
                    date="",
                    message="Uncommitted changes",
                    diff=uncommitted,
                )
            )

        return commits
