"""Auth API routes: login, token validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from kannix.deps import AppDeps


class LoginRequest(BaseModel):
    """Login request body."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response body."""

    username: str
    token: str
    is_admin: bool


class MeResponse(BaseModel):
    """Current user info response."""

    id: str
    username: str
    is_admin: bool


def create_auth_router(deps: AppDeps) -> APIRouter:
    """Create auth API router."""
    router = APIRouter()

    @router.post("/login", response_model=LoginResponse)
    async def login(body: LoginRequest) -> LoginResponse:
        user = deps.auth_manager.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return LoginResponse(
            username=user.username,
            token=user.token,
            is_admin=user.is_admin,
        )

    @router.get("/me", response_model=MeResponse)
    async def me(
        authorization: str = Header(default=""),
    ) -> MeResponse:
        token = _extract_bearer_token(authorization)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing or invalid token")
        user = deps.auth_manager.validate_token(token)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return MeResponse(
            id=user.id,
            username=user.username,
            is_admin=user.is_admin,
        )

    return router


def _extract_bearer_token(authorization: str) -> str | None:
    """Extract token from 'Bearer <token>' header value."""
    if not authorization.startswith("Bearer "):
        return None
    return authorization[7:]
