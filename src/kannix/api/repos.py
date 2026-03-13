"""Repo API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from kannix.deps import AppDeps


class CloneRepoRequest(BaseModel):
    """Clone repo request."""

    url: str
    name: str | None = None


class AssignRepoRequest(BaseModel):
    """Assign/unassign repo request."""

    repo_id: str
    ticket_id: str


class RepoResponse(BaseModel):
    """Repo response."""

    id: str
    name: str
    url: str
    path: str
    default_branch: str


def _require_auth(deps: AppDeps, authorization: str) -> None:
    """Validate auth token."""
    from kannix.api.auth import _extract_bearer_token

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing token")
    user = deps.auth_manager.validate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_repos_router(deps: AppDeps) -> APIRouter:
    """Create repos API router."""
    router = APIRouter()

    @router.get("", response_model=list[RepoResponse])
    async def list_repos(
        authorization: str = Header(default=""),
    ) -> list[RepoResponse]:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            return []
        repos = deps.git_manager.list_repos()
        return [
            RepoResponse(
                id=r.id,
                name=r.name,
                url=r.url,
                path=r.path,
                default_branch=r.default_branch,
            )
            for r in repos
        ]

    @router.post("", response_model=RepoResponse, status_code=201)
    async def clone_repo(
        body: CloneRepoRequest,
        authorization: str = Header(default=""),
    ) -> RepoResponse:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            raise HTTPException(
                status_code=400, detail="Git not configured (repos_dir/worktree_dir)"
            )
        try:
            repo = deps.git_manager.clone_repo(body.url, name=body.name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return RepoResponse(
            id=repo.id,
            name=repo.name,
            url=repo.url,
            path=repo.path,
            default_branch=repo.default_branch,
        )

    @router.get("/{repo_id}", response_model=RepoResponse)
    async def get_repo(
        repo_id: str,
        authorization: str = Header(default=""),
    ) -> RepoResponse:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            raise HTTPException(status_code=404, detail="Repo not found")
        repo = deps.git_manager.get_repo(repo_id)
        if repo is None:
            raise HTTPException(status_code=404, detail="Repo not found")
        return RepoResponse(
            id=repo.id,
            name=repo.name,
            url=repo.url,
            path=repo.path,
            default_branch=repo.default_branch,
        )

    @router.post("/assign")
    async def assign_repo(
        body: AssignRepoRequest,
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            raise HTTPException(status_code=400, detail="Git not configured")
        state = deps.state_manager.load()
        ticket_state = state.tickets.get(body.ticket_id)
        if ticket_state is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if body.repo_id not in state.repos:
            raise HTTPException(status_code=404, detail="Repo not found")
        if body.repo_id not in ticket_state.repos:
            ticket_state.repos.append(body.repo_id)
            deps.state_manager.save(state)
        try:
            deps.git_manager.create_worktree(body.repo_id, body.ticket_id, ticket_state.title)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"status": "assigned"}

    @router.post("/unassign")
    async def unassign_repo(
        body: AssignRepoRequest,
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            raise HTTPException(status_code=400, detail="Git not configured")
        state = deps.state_manager.load()
        ticket_state = state.tickets.get(body.ticket_id)
        if ticket_state is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if body.repo_id in ticket_state.repos:
            ticket_state.repos.remove(body.repo_id)
            deps.state_manager.save(state)
        deps.git_manager.delete_worktree(body.repo_id, body.ticket_id)
        return {"status": "unassigned"}

    @router.delete("/{repo_id}")
    async def delete_repo(
        repo_id: str,
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        _require_auth(deps, authorization)
        if deps.git_manager is None:
            raise HTTPException(status_code=404, detail="Repo not found")
        if not deps.git_manager.delete_repo(repo_id):
            raise HTTPException(status_code=404, detail="Repo not found")
        return {"status": "deleted"}

    return router
