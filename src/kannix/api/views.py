"""HTML view routes (HTMX frontend)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from kannix.tickets import TicketManager

if TYPE_CHECKING:
    from kannix.deps import AppDeps
    from kannix.state import TicketState, UserState

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
AVAILABLE_THEMES = ["midnight", "light", "solarized", "nord", "dracula"]
DEFAULT_THEME = "midnight"


def _get_theme(theme_cookie: str | None) -> str:
    """Get validated theme name from cookie, falling back to default."""
    if theme_cookie and theme_cookie in AVAILABLE_THEMES:
        return theme_cookie
    return DEFAULT_THEME


def _get_user(deps: AppDeps, token: str | None) -> UserState | None:
    """Validate token from cookie."""
    if token is None:
        return None
    return deps.auth_manager.validate_token(token)


def _tickets_by_column(
    tickets: list[TicketState], columns: list[str]
) -> dict[str, list[TicketState]]:
    """Group tickets by column."""
    result: dict[str, list[TicketState]] = {c: [] for c in columns}
    for t in tickets:
        if t.column in result:
            result[t.column].append(t)
    return result


def create_views_router(deps: AppDeps) -> APIRouter:
    """Create HTML view router."""
    router = APIRouter()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    ticket_mgr = TicketManager(deps.state_manager, deps.config)

    @router.get("/")
    async def root(
        token: str | None = Cookie(default=None),
    ) -> RedirectResponse:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        return RedirectResponse(url="/board", status_code=302)

    @router.get("/login", response_class=HTMLResponse)
    async def login_page(
        request: Request,
        theme: str | None = Cookie(default=None),
    ) -> Response:
        return templates.TemplateResponse(
            request, "login.html", {"error": None, "theme": _get_theme(theme)}
        )

    @router.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(),
        password: str = Form(),
    ) -> Response:
        user = deps.auth_manager.authenticate(username, password)
        if user is None:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid username or password"},
            )
        response = RedirectResponse(url="/board", status_code=303)
        response.set_cookie("token", user.token, httponly=True)
        return response

    @router.get("/ticket/{ticket_id}")
    async def ticket_detail(
        request: Request,
        ticket_id: str,
        token: str | None = Cookie(default=None),
        theme: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket_mgr_local = TicketManager(deps.state_manager, deps.config)
        ticket = ticket_mgr_local.get(ticket_id)
        if ticket is None:
            return HTMLResponse("Ticket not found", status_code=404)
        return templates.TemplateResponse(
            request,
            "ticket.html",
            {"ticket": ticket, "token": token, "theme": _get_theme(theme)},
        )

    @router.get("/board")
    async def board(
        request: Request,
        token: str | None = Cookie(default=None),
        theme: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        tickets = ticket_mgr.list_all()
        by_col = _tickets_by_column(tickets, deps.config.columns)
        current_theme = _get_theme(theme)
        return templates.TemplateResponse(
            request,
            "board.html",
            {
                "columns": deps.config.columns,
                "tickets_by_column": by_col,
                "username": user.username,
                "theme": current_theme,
                "themes": AVAILABLE_THEMES,
            },
        )

    return router


def create_htmx_router(deps: AppDeps) -> APIRouter:
    """Create HTMX partial response router."""
    router = APIRouter()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    ticket_mgr = TicketManager(deps.state_manager, deps.config)

    @router.post("/tickets")
    async def create_ticket(
        request: Request,
        title: str = Form(),
        description: str = Form(default=""),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket = ticket_mgr.create(title, description)
        return templates.TemplateResponse(
            request,
            "partials/ticket_card.html",
            {"ticket": ticket},
        )

    @router.put("/tickets/{ticket_id}")
    async def update_ticket(
        request: Request,
        ticket_id: str,
        title: str = Form(default=""),
        description: str = Form(default=""),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket = ticket_mgr.update(
            ticket_id,
            title=title or None,
            description=description,
        )
        if ticket is None:
            return HTMLResponse("Ticket not found", status_code=404)
        return HTMLResponse("<div style='color: #4ade80;'>✓ Saved</div>")

    @router.get("/tickets/{ticket_id}/fields")
    async def ticket_fields(
        request: Request,
        ticket_id: str,
        token: str | None = Cookie(default=None),
    ) -> Response:
        """Return ticket fields partial for live polling."""
        user = _get_user(deps, token)
        if user is None:
            return HTMLResponse("", status_code=401)
        ticket_mgr_local = TicketManager(deps.state_manager, deps.config)
        ticket = ticket_mgr_local.get(ticket_id)
        if ticket is None:
            return HTMLResponse("", status_code=404)
        return templates.TemplateResponse(
            request,
            "partials/ticket_fields.html",
            {"ticket": ticket},
        )

    @router.post("/tickets/{ticket_id}/move")
    async def move_ticket(
        request: Request,
        ticket_id: str,
        column: str = Form(),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket = ticket_mgr.move(ticket_id, column)
        if ticket is None:
            return HTMLResponse("Ticket not found", status_code=404)
        return templates.TemplateResponse(
            request,
            "partials/ticket_card.html",
            {"ticket": ticket},
        )

    return router
