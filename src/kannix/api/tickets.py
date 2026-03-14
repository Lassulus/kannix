"""Ticket API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, field_validator

from kannix.tickets import TicketManager

if TYPE_CHECKING:
    from kannix.deps import AppDeps
    from kannix.state import UserState


class CreateTicketRequest(BaseModel):
    """Create ticket request."""

    title: str
    description: str = ""

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be blank")
        return v.strip()


class UpdateTicketRequest(BaseModel):
    """Update ticket request."""

    description: str | None = None
    assigned_to: str | None = None


class MoveTicketRequest(BaseModel):
    """Move ticket request."""

    column: str


class TicketResponse(BaseModel):
    """Ticket response."""

    id: str
    title: str
    description: str
    column: str
    assigned_to: str | None


def _require_auth(deps: AppDeps, authorization: str) -> UserState:
    """Extract and validate user from auth header."""
    from kannix.api.auth import _extract_bearer_token

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    user = deps.auth_manager.validate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def create_tickets_router(deps: AppDeps) -> APIRouter:
    """Create tickets API router."""
    router = APIRouter()
    ticket_mgr = TicketManager(deps.state_manager, deps.config)

    @router.post("", response_model=TicketResponse, status_code=201)
    async def create_ticket(
        body: CreateTicketRequest,
        authorization: str = Header(default=""),
    ) -> TicketResponse:
        _require_auth(deps, authorization)
        ticket = ticket_mgr.create(body.title, body.description)
        return TicketResponse(
            id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            column=ticket.column,
            assigned_to=ticket.assigned_to,
        )

    @router.get("", response_model=list[TicketResponse])
    async def list_tickets(
        authorization: str = Header(default=""),
    ) -> list[TicketResponse]:
        _require_auth(deps, authorization)
        tickets = ticket_mgr.list_all()
        return [
            TicketResponse(
                id=t.id,
                title=t.title,
                description=t.description,
                column=t.column,
                assigned_to=t.assigned_to,
            )
            for t in tickets
        ]

    @router.get("/{ticket_id}", response_model=TicketResponse)
    async def get_ticket(
        ticket_id: str,
        authorization: str = Header(default=""),
    ) -> TicketResponse:
        _require_auth(deps, authorization)
        ticket = ticket_mgr.get(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return TicketResponse(
            id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            column=ticket.column,
            assigned_to=ticket.assigned_to,
        )

    @router.put("/{ticket_id}", response_model=TicketResponse)
    async def update_ticket(
        ticket_id: str,
        body: UpdateTicketRequest,
        authorization: str = Header(default=""),
    ) -> TicketResponse:
        _require_auth(deps, authorization)
        ticket = ticket_mgr.update(
            ticket_id,
            description=body.description,
        )
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return TicketResponse(
            id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            column=ticket.column,
            assigned_to=ticket.assigned_to,
        )

    @router.delete("/{ticket_id}")
    async def delete_ticket(
        ticket_id: str,
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        _require_auth(deps, authorization)
        if not ticket_mgr.delete(ticket_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {"status": "deleted"}

    @router.post("/{ticket_id}/move", response_model=TicketResponse)
    async def move_ticket(
        ticket_id: str,
        body: MoveTicketRequest,
        authorization: str = Header(default=""),
    ) -> TicketResponse:
        _require_auth(deps, authorization)
        try:
            ticket = ticket_mgr.move(ticket_id, body.column)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return TicketResponse(
            id=ticket.id,
            title=ticket.title,
            description=ticket.description,
            column=ticket.column,
            assigned_to=ticket.assigned_to,
        )

    return router
