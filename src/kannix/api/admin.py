"""Admin API routes: user management."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from kannix.deps import AppDeps
    from kannix.state import UserState


class CreateUserRequest(BaseModel):
    """Create user request body."""

    username: str
    password: str
    is_admin: bool = False


class UserResponse(BaseModel):
    """User response (no password_hash)."""

    id: str
    username: str
    token: str
    is_admin: bool


def _require_admin(deps: AppDeps, authorization: str) -> UserState:
    """Extract and validate admin user from auth header.

    Raises:
        HTTPException: 401 if no/invalid token, 403 if not admin.
    """
    from kannix.api.auth import _extract_bearer_token

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    user = deps.auth_manager.validate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def create_admin_router(deps: AppDeps) -> APIRouter:
    """Create admin API router."""
    router = APIRouter()

    @router.post("/users", response_model=UserResponse, status_code=201)
    async def create_user(
        body: CreateUserRequest,
        authorization: str = Header(default=""),
    ) -> UserResponse:
        _require_admin(deps, authorization)
        try:
            user = deps.auth_manager.create_user(
                body.username, body.password, is_admin=body.is_admin
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return UserResponse(
            id=user.id,
            username=user.username,
            token=user.token,
            is_admin=user.is_admin,
        )

    @router.get("/users", response_model=list[UserResponse])
    async def list_users(
        authorization: str = Header(default=""),
    ) -> list[UserResponse]:
        _require_admin(deps, authorization)
        state = deps.state_manager.load()
        return [
            UserResponse(
                id=u.id,
                username=u.username,
                token=u.token,
                is_admin=u.is_admin,
            )
            for u in state.users.values()
        ]

    @router.delete("/users/{user_id}")
    async def delete_user(
        user_id: str,
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        _require_admin(deps, authorization)
        state = deps.state_manager.load()
        if user_id not in state.users:
            raise HTTPException(status_code=404, detail="User not found")
        del state.users[user_id]
        deps.state_manager.save(state)
        return {"status": "deleted"}

    @router.post("/users/{user_id}/reset-token", response_model=UserResponse)
    async def reset_token(
        user_id: str,
        authorization: str = Header(default=""),
    ) -> UserResponse:
        _require_admin(deps, authorization)
        state = deps.state_manager.load()
        if user_id not in state.users:
            raise HTTPException(status_code=404, detail="User not found")
        user = state.users[user_id]
        from kannix.state import UserState

        state.users[user_id] = UserState(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            token=secrets.token_urlsafe(32),
            is_admin=user.is_admin,
        )
        deps.state_manager.save(state)
        updated = state.users[user_id]
        return UserResponse(
            id=updated.id,
            username=updated.username,
            token=updated.token,
            is_admin=updated.is_admin,
        )

    return router
