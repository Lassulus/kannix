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
    ticket_mgr = TicketManager(
        deps.state_manager,
        deps.config,
        hook_executor=deps.hook_executor,
        git_manager=deps.git_manager,
    )

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
        if ticket is None or ticket.archived:
            return RedirectResponse(url="/board", status_code=302)

        # Get repo info for assignment UI
        all_repos = deps.git_manager.list_repos() if deps.git_manager else []
        assigned_repos = [r for r in all_repos if r.id in ticket.repos]
        unassigned_repos = [r for r in all_repos if r.id not in ticket.repos]
        git_enabled = deps.git_manager is not None

        return templates.TemplateResponse(
            request,
            "ticket.html",
            {
                "ticket": ticket,
                "token": token,
                "theme": _get_theme(theme),
                "assigned_repos": assigned_repos,
                "unassigned_repos": unassigned_repos,
                "git_enabled": git_enabled,
            },
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

    @router.get("/ticket/{ticket_id}/diff")
    async def ticket_diff_page(
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

        all_repos = deps.git_manager.list_repos() if deps.git_manager else []
        assigned_repos = [r for r in all_repos if r.id in ticket.repos]

        # Get commits and diffs for all assigned repos
        from kannix.git import CommitInfo  # noqa: TC001

        commits_by_repo: dict[str, list[CommitInfo]] = {}
        diffs: dict[str, str] = {}
        for repo in assigned_repos:
            if deps.git_manager:
                commits_by_repo[repo.id] = deps.git_manager.get_commits(repo.id, ticket_id)
                diffs[repo.id] = deps.git_manager.get_diff(repo.id, ticket_id)

        # Serialize commits for template (tojson filter handles HTML escaping)
        commits_data: dict[str, list[dict[str, str]]] = {}
        for repo_id, commits in commits_by_repo.items():
            commits_data[repo_id] = [
                {
                    "sha": c.sha,
                    "author": c.author,
                    "date": c.date,
                    "message": c.message,
                    "diff": c.diff,
                }
                for c in commits
            ]

        return templates.TemplateResponse(
            request,
            "diff.html",
            {
                "ticket": ticket,
                "assigned_repos": assigned_repos,
                "diffs": diffs,
                "commits_data": commits_data,
                "theme": _get_theme(theme),
            },
        )

    @router.get("/repos")
    async def repos_page(
        request: Request,
        token: str | None = Cookie(default=None),
        theme: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        repos = deps.git_manager.list_repos() if deps.git_manager else []
        git_enabled = deps.git_manager is not None
        return templates.TemplateResponse(
            request,
            "repos.html",
            {
                "repos": repos,
                "git_enabled": git_enabled,
                "username": user.username,
                "theme": _get_theme(theme),
                "themes": AVAILABLE_THEMES,
            },
        )

    return router


async def _render_repos_section(
    request: Request,
    ticket_id: str,
    deps: AppDeps,
    templates: Jinja2Templates,
) -> Response:
    """Render the repos section partial for a ticket."""
    ticket_mgr = TicketManager(deps.state_manager, deps.config)
    ticket = ticket_mgr.get(ticket_id)
    if ticket is None:
        return HTMLResponse("Ticket not found", status_code=404)
    all_repos = deps.git_manager.list_repos() if deps.git_manager else []
    assigned = [r for r in all_repos if r.id in ticket.repos]
    unassigned = [r for r in all_repos if r.id not in ticket.repos]
    return templates.TemplateResponse(
        request,
        "partials/ticket_repos.html",
        {
            "ticket": ticket,
            "assigned_repos": assigned,
            "unassigned_repos": unassigned,
        },
    )


def create_htmx_router(deps: AppDeps) -> APIRouter:
    """Create HTMX partial response router."""
    router = APIRouter()
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    ticket_mgr = TicketManager(
        deps.state_manager,
        deps.config,
        hook_executor=deps.hook_executor,
        git_manager=deps.git_manager,
    )

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
        ticket = await ticket_mgr.create_async(title, description)
        return templates.TemplateResponse(
            request,
            "partials/ticket_card.html",
            {"ticket": ticket},
        )

    @router.put("/tickets/{ticket_id}")
    async def update_ticket(
        request: Request,
        ticket_id: str,
        description: str = Form(default=""),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket = ticket_mgr.update(
            ticket_id,
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
        if ticket is None or ticket.archived:
            return HTMLResponse("", status_code=404)
        return templates.TemplateResponse(
            request,
            "partials/ticket_fields.html",
            {"ticket": ticket},
        )

    @router.post("/repos/clone")
    async def clone_repo_htmx(
        request: Request,
        url: str = Form(),
        name: str = Form(default=""),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        if deps.git_manager is None:
            return HTMLResponse("Git not configured", status_code=400)
        try:
            repo = deps.git_manager.clone_repo(url, name=name or None)
        except Exception as e:
            return HTMLResponse(
                f"<div class='error'>Clone failed: {e}</div>",
                status_code=400,
            )
        return templates.TemplateResponse(
            request,
            "partials/repo_row.html",
            {"repo": repo},
        )

    @router.post("/tickets/{ticket_id}/assign-repo")
    async def assign_repo_htmx(
        request: Request,
        ticket_id: str,
        repo_id: str = Form(),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        if deps.git_manager is None:
            return HTMLResponse("Git not configured", status_code=400)

        # Add repo to ticket
        state = deps.state_manager.load()
        ticket_state = state.tickets.get(ticket_id)
        if ticket_state is None:
            return HTMLResponse("Ticket not found", status_code=404)
        if repo_id not in ticket_state.repos:
            ticket_state.repos.append(repo_id)
            deps.state_manager.save(state)

        # Create worktree
        try:
            deps.git_manager.create_worktree(repo_id, ticket_id, ticket_state.title)
        except Exception as e:
            return HTMLResponse(f"<div class='error'>Worktree failed: {e}</div>")

        # Return updated repos section
        return await _render_repos_section(request, ticket_id, deps, templates)

    @router.post("/tickets/{ticket_id}/unassign-repo")
    async def unassign_repo_htmx(
        request: Request,
        ticket_id: str,
        repo_id: str = Form(),
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        if deps.git_manager is None:
            return HTMLResponse("Git not configured", status_code=400)

        # Remove repo from ticket
        state = deps.state_manager.load()
        ticket_state = state.tickets.get(ticket_id)
        if ticket_state is None:
            return HTMLResponse("Ticket not found", status_code=404)
        if repo_id in ticket_state.repos:
            ticket_state.repos.remove(repo_id)
            deps.state_manager.save(state)

        # Delete worktree
        deps.git_manager.delete_worktree(repo_id, ticket_id)

        return await _render_repos_section(request, ticket_id, deps, templates)

    @router.delete("/repos/{repo_id}")
    async def delete_repo_htmx(
        request: Request,
        repo_id: str,
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        if deps.git_manager is None:
            return HTMLResponse("", status_code=404)
        deps.git_manager.delete_repo(repo_id)
        return HTMLResponse("")

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

    @router.post("/tickets/{ticket_id}/archive")
    async def archive_ticket(
        request: Request,
        ticket_id: str,
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        ticket = await ticket_mgr.archive_async(ticket_id)
        if ticket is None:
            return HTMLResponse("Ticket not found", status_code=404)
        # Kill the tmux session for this ticket
        if deps.tmux_manager is not None:
            deps.tmux_manager.kill_session(ticket_id)
        # Return empty content so the card is removed from the board
        return HTMLResponse("")

    @router.delete("/tickets/{ticket_id}")
    async def delete_ticket(
        request: Request,
        ticket_id: str,
        token: str | None = Cookie(default=None),
    ) -> Response:
        user = _get_user(deps, token)
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        # Kill the tmux session before deleting
        if deps.tmux_manager is not None:
            deps.tmux_manager.kill_session(ticket_id)
        if not await ticket_mgr.delete_async(ticket_id):
            return HTMLResponse("Ticket not found", status_code=404)
        # Return empty content so the card is removed from the board
        return HTMLResponse("")

    return router
