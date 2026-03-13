"""Columns API route."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException

if TYPE_CHECKING:
    from kannix.deps import AppDeps


def create_columns_router(deps: AppDeps) -> APIRouter:
    """Create columns API router."""
    router = APIRouter()

    @router.get("/columns")
    async def list_columns(
        authorization: str = Header(default=""),
    ) -> list[str]:
        from kannix.api.auth import _extract_bearer_token

        token = _extract_bearer_token(authorization)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing token")
        user = deps.auth_manager.validate_token(token)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return deps.config.columns

    return router
