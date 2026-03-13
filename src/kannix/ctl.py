"""kannix-ctl — CLI tool for managing tickets from within tmux sessions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError


def _get_env() -> tuple[str, str, str]:
    """Read required env vars, exit if missing."""
    url = os.environ.get("KANNIX_URL", "")
    token = os.environ.get("KANNIX_TOKEN", "")
    ticket_id = os.environ.get("KANNIX_TICKET_ID", "")
    if not url or not token:
        print(
            "Error: KANNIX_URL and KANNIX_TOKEN must be set.\n"
            "These are normally set automatically in kannix tmux sessions.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, token, ticket_id


def _http_request(
    url: str, *, method: str = "GET", token: str, data: dict[str, object] | None = None
) -> tuple[int, str]:
    """Make an HTTP request. Returns (status_code, response_body)."""
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()
    except URLError as e:
        print(f"Error: Could not connect to {url}: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_get(args: argparse.Namespace) -> None:
    """Get current ticket info."""
    url, token, ticket_id = _get_env()
    if not ticket_id:
        print("Error: KANNIX_TICKET_ID not set.", file=sys.stderr)
        sys.exit(1)
    status, body = _http_request(f"{url}/api/tickets/{ticket_id}", token=token)
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(body), indent=2))


def _cmd_set(args: argparse.Namespace) -> None:
    """Update ticket fields."""
    url, token, ticket_id = _get_env()
    if not ticket_id:
        print("Error: KANNIX_TICKET_ID not set.", file=sys.stderr)
        sys.exit(1)
    data: dict[str, object] = {}
    if args.title is not None:
        data["title"] = args.title
    if args.description is not None:
        data["description"] = args.description
    if not data:
        print("Error: provide --title and/or --description", file=sys.stderr)
        sys.exit(1)
    status, body = _http_request(
        f"{url}/api/tickets/{ticket_id}", method="PUT", token=token, data=data
    )
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(body), indent=2))


def _cmd_move(args: argparse.Namespace) -> None:
    """Move ticket to a column."""
    url, token, ticket_id = _get_env()
    if not ticket_id:
        print("Error: KANNIX_TICKET_ID not set.", file=sys.stderr)
        sys.exit(1)
    column = args.column
    status, body = _http_request(
        f"{url}/api/tickets/{ticket_id}/move",
        method="POST",
        token=token,
        data={"column": column},
    )
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(body), indent=2))


def _cmd_list_columns(args: argparse.Namespace) -> None:
    """List available columns."""
    url, token, _ticket_id = _get_env()
    status, body = _http_request(f"{url}/api/columns", token=token)
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    columns = json.loads(body)
    for col in columns:
        print(col)


def _cmd_list_tickets(args: argparse.Namespace) -> None:
    """List all tickets."""
    url, token, _ticket_id = _get_env()
    status, body = _http_request(f"{url}/api/tickets", token=token)
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    tickets = json.loads(body)
    for t in tickets:
        marker = " *" if t["id"] == os.environ.get("KANNIX_TICKET_ID") else ""
        print(f"[{t['column']}] {t['title']} ({t['id'][:8]}){marker}")


def _cmd_clone_repo(args: argparse.Namespace) -> None:
    """Clone a repo by URL."""
    url, token, _ticket_id = _get_env()
    data: dict[str, object] = {"url": args.url}
    if args.name:
        data["name"] = args.name
    status, body = _http_request(f"{url}/api/repos", method="POST", token=token, data=data)
    if status not in (200, 201):
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    repo = json.loads(body)
    print(f"Cloned {repo['name']} ({repo['id'][:8]}) [{repo['default_branch']}]")


def _cmd_delete_repo(args: argparse.Namespace) -> None:
    """Delete a repo."""
    url, token, _ticket_id = _get_env()
    status, body = _http_request(f"{url}/api/repos/{args.repo_id}", method="DELETE", token=token)
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Deleted repo {args.repo_id[:8]}")


def _cmd_list_repos(args: argparse.Namespace) -> None:
    """List all repos."""
    url, token, _ticket_id = _get_env()
    status, body = _http_request(f"{url}/api/repos", token=token)
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    repos = json.loads(body)
    for r in repos:
        print(f"{r['name']} ({r['id'][:8]}) — {r['url']} [{r['default_branch']}]")


def _cmd_assign_repo(args: argparse.Namespace) -> None:
    """Assign a repo to the current ticket."""
    url, token, ticket_id = _get_env()
    if not ticket_id:
        print("Error: KANNIX_TICKET_ID not set.", file=sys.stderr)
        sys.exit(1)
    data = {"repo_id": args.repo_id, "ticket_id": ticket_id}
    status, body = _http_request(f"{url}/api/repos/assign", method="POST", token=token, data=data)
    if status not in (200, 201):
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Repo {args.repo_id[:8]} assigned to ticket {ticket_id[:8]}")


def _cmd_unassign_repo(args: argparse.Namespace) -> None:
    """Unassign a repo from the current ticket."""
    url, token, ticket_id = _get_env()
    if not ticket_id:
        print("Error: KANNIX_TICKET_ID not set.", file=sys.stderr)
        sys.exit(1)
    data = {"repo_id": args.repo_id, "ticket_id": ticket_id}
    status, body = _http_request(
        f"{url}/api/repos/unassign", method="POST", token=token, data=data
    )
    if status != 200:
        print(f"Error ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Repo {args.repo_id[:8]} unassigned from ticket {ticket_id[:8]}")


def _cmd_worktrees(args: argparse.Namespace) -> None:
    """Show worktree paths for current ticket."""
    _url, _token, _ticket_id = _get_env()
    found = False
    for key, value in sorted(os.environ.items()):
        if key.startswith("KANNIX_WORKTREE_"):
            repo_name = key[len("KANNIX_WORKTREE_") :].lower().replace("_", "-")
            print(f"{repo_name}: {value}")
            found = True
    if not found:
        print("No worktrees assigned to this ticket.", file=sys.stderr)


def main() -> None:
    """Entry point for kannix-ctl."""
    parser = argparse.ArgumentParser(
        prog="kannix-ctl",
        description="Manage kannix tickets from the terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("get", help="Show current ticket info")

    set_parser = sub.add_parser("set", help="Update ticket fields")
    set_parser.add_argument("--title", help="New title")
    set_parser.add_argument("--description", help="New description")

    move_parser = sub.add_parser("move", help="Move ticket to a column")
    move_parser.add_argument("column", help="Target column name")

    sub.add_parser("list-columns", help="List available columns")
    sub.add_parser("list-tickets", help="List all tickets")
    clone_parser = sub.add_parser("clone-repo", help="Clone a repo by URL")
    clone_parser.add_argument("url", help="Git clone URL")
    clone_parser.add_argument("--name", help="Custom name (default: derived from URL)")

    delete_repo_parser = sub.add_parser("delete-repo", help="Delete a repo")
    delete_repo_parser.add_argument("repo_id", help="Repo ID")

    sub.add_parser("list-repos", help="List all repos")

    assign_parser = sub.add_parser("assign-repo", help="Assign a repo to current ticket")
    assign_parser.add_argument("repo_id", help="Repo ID (or prefix)")

    unassign_parser = sub.add_parser("unassign-repo", help="Unassign a repo from current ticket")
    unassign_parser.add_argument("repo_id", help="Repo ID (or prefix)")

    sub.add_parser("worktrees", help="Show worktree paths for this ticket")

    args = parser.parse_args()

    commands = {
        "get": _cmd_get,
        "set": _cmd_set,
        "move": _cmd_move,
        "list-columns": _cmd_list_columns,
        "list-tickets": _cmd_list_tickets,
        "clone-repo": _cmd_clone_repo,
        "delete-repo": _cmd_delete_repo,
        "list-repos": _cmd_list_repos,
        "assign-repo": _cmd_assign_repo,
        "unassign-repo": _cmd_unassign_repo,
        "worktrees": _cmd_worktrees,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
