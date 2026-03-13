# Kannix

A web-based kanban board where each ticket has an attached **tmux terminal session**, accessible directly in the browser via xterm.js. Configurable lifecycle hooks run shell commands when tickets are created, moved between columns, or deleted.

## Features

- **Kanban board** with configurable columns and drag-and-drop (SortableJS + HTMX)
- **Embedded terminal** per ticket — each ticket gets a tmux session viewable in the browser via xterm.js
- **Lifecycle hooks** — run shell commands on ticket create/move/delete with environment variables
- **Multi-user auth** — token-based login, admin user management
- **JSON config** — simple configuration file for columns, hooks, and server settings
- **JSON state** — human-readable state file with file locking
- **NixOS module** — deploy as a systemd service with declarative config

## Quick Start

### With Nix (development)

```bash
git clone <repo> && cd kannix
nix develop

# Create a config file
cat > kannix.json << 'EOF'
{
  "columns": ["Backlog", "In Progress", "Review", "Done"],
  "hooks": {
    "on_create": "tmux -L kannix new-session -d -s $TICKET_ID",
    "on_delete": "tmux -L kannix kill-session -t $TICKET_ID"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8080
  }
}
EOF

# Seed an admin user
python -c "
from pathlib import Path
from kannix.auth import AuthManager
from kannix.state import StateManager
auth = AuthManager(StateManager(Path('state.json')))
user = auth.create_user('admin', 'admin', is_admin=True)
print(f'Admin token: {user.token}')
"

# Run the server
python -m kannix.main kannix.json .
```

Then open http://127.0.0.1:8080 and log in with `admin` / `admin`.

### With Nix (build)

```bash
nix build
./result/bin/kannix kannix.json /path/to/state/dir
```

## Configuration

### `kannix.json`

```json
{
  "columns": ["Backlog", "In Progress", "Review", "Done"],
  "hooks": {
    "on_create": "tmux -L kannix new-session -d -s $TICKET_ID",
    "on_move": {
      "Backlog->In Progress": "echo 'Starting work on $TICKET_TITLE'",
      "Review->Done": "echo 'Completed $TICKET_TITLE'"
    },
    "on_delete": "tmux -L kannix kill-session -t $TICKET_ID"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8080
  }
}
```

### Config Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `columns` | `string[]` | **(required)** | Kanban column names, in order. Must be non-empty and unique. |
| `hooks.on_create` | `string\|null` | `null` | Shell command run when a ticket is created. |
| `hooks.on_move` | `object` | `{}` | Map of `"From->To"` column transitions to shell commands. |
| `hooks.on_delete` | `string\|null` | `null` | Shell command run when a ticket is deleted. |
| `server.host` | `string` | `"0.0.0.0"` | Host to bind to. |
| `server.port` | `integer` | `8080` | Port to listen on. |

### Hook Environment Variables

All hook commands receive these environment variables:

| Variable | Description |
|----------|-------------|
| `TICKET_ID` | Unique ticket identifier (hex string) |
| `TICKET_TITLE` | Ticket title |
| `TICKET_COLUMN` | Current column (or target column for moves) |
| `TICKET_PREV_COLUMN` | Previous column (only for `on_move` hooks) |
| `TMUX_SESSION` | Tmux session name (same as `TICKET_ID`) |

## NixOS Module

Add to your flake inputs:

```nix
{
  inputs.kannix.url = "github:you/kannix";
}
```

Then in your NixOS configuration:

```nix
{ inputs, ... }:
{
  imports = [ inputs.kannix.nixosModules.default ];

  services.kannix = {
    enable = true;
    port = 8080;
    columns = [ "Backlog" "In Progress" "Review" "Done" ];
    hooks = {
      onCreate = "tmux -L kannix new-session -d -s $TICKET_ID";
      onMove = {
        "Backlog->In Progress" = "echo starting";
      };
      onDelete = "tmux -L kannix kill-session -t $TICKET_ID";
    };
    openFirewall = true;
  };
}
```

### NixOS Module Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | `bool` | `false` | Enable the Kannix service. |
| `host` | `string` | `"0.0.0.0"` | Host to bind to. |
| `port` | `port` | `8080` | Port to listen on. |
| `stateDir` | `path` | `/var/lib/kannix` | Directory for state file. |
| `columns` | `list of string` | `["Backlog" "In Progress" "Review" "Done"]` | Column names. |
| `hooks.onCreate` | `null or string` | `null` | Hook command on ticket creation. |
| `hooks.onMove` | `attrs of string` | `{}` | Hook commands for column transitions. |
| `hooks.onDelete` | `null or string` | `null` | Hook command on ticket deletion. |
| `user` | `string` | `"kannix"` | System user. |
| `group` | `string` | `"kannix"` | System group. |
| `openFirewall` | `bool` | `false` | Open port in firewall. |

## API

All API endpoints require `Authorization: Bearer <token>` header.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Login with `{username, password}`, returns token |
| `GET` | `/api/auth/me` | Current user info |
| `POST` | `/api/admin/users` | Create user (admin only) |
| `GET` | `/api/admin/users` | List users (admin only) |
| `DELETE` | `/api/admin/users/{id}` | Delete user (admin only) |
| `POST` | `/api/admin/users/{id}/reset-token` | Reset user token (admin only) |
| `POST` | `/api/tickets` | Create ticket |
| `GET` | `/api/tickets` | List all tickets |
| `GET` | `/api/tickets/{id}` | Get ticket |
| `PUT` | `/api/tickets/{id}` | Update ticket |
| `DELETE` | `/api/tickets/{id}` | Delete ticket |
| `POST` | `/api/tickets/{id}/move` | Move ticket to column |
| `WS` | `/ws/terminal/{ticket_id}?token=<token>` | Terminal WebSocket |

## Development

```bash
nix develop

# Run all checks (same as nix flake check)
ruff check src/ tests/
ruff format --check src/ tests/
mypy --strict src/
pytest -v

# Or just:
nix flake check
```

### Project Structure

```
src/kannix/
├── __init__.py
├── main.py          # Entry point
├── app.py           # FastAPI app factory
├── config.py        # Config loading (pydantic)
├── state.py         # JSON state persistence
├── auth.py          # User auth + password hashing
├── tickets.py       # Ticket CRUD logic
├── hooks.py         # Hook execution engine
├── tmux.py          # Tmux session management
├── deps.py          # Dependency container
├── api/
│   ├── auth.py      # Auth endpoints
│   ├── admin.py     # Admin endpoints
│   ├── tickets.py   # Ticket endpoints
│   ├── views.py     # HTML views (HTMX)
│   └── terminal.py  # WebSocket terminal proxy
└── templates/
    ├── base.html
    ├── login.html
    ├── board.html
    ├── ticket.html
    └── partials/
        └── ticket_card.html
```

## License

MIT
