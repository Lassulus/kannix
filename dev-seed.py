"""Seed script: create admin user for dev testing."""

from pathlib import Path

from kannix.auth import AuthManager
from kannix.state import StateManager

state = StateManager(Path("/tmp/kannix-dev/state.json"))
auth = AuthManager(state)

try:
    user = auth.create_user("admin", "admin", is_admin=True)
    print(f"Created admin user: {user.username}")
    print(f"Token: {user.token}")
except ValueError:
    print("Admin user already exists")
    s = state.load()
    for u in s.users.values():
        if u.username == "admin":
            print(f"Token: {u.token}")
