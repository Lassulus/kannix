"""Authentication: password hashing, user management, token validation."""

from __future__ import annotations

import secrets
import uuid

import bcrypt

from kannix.state import StateManager, UserState


class AuthManager:
    """Manages user authentication, creation, and token validation."""

    def __init__(self, state_manager: StateManager) -> None:
        self._state = state_manager

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against a bcrypt hash."""
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def create_user(self, username: str, password: str, *, is_admin: bool) -> UserState:
        """Create a new user and persist to state.

        Args:
            username: Unique username.
            password: Plain-text password (will be hashed).
            is_admin: Whether the user has admin privileges.

        Returns:
            The created UserState.

        Raises:
            ValueError: If username already exists.
        """
        state = self._state.load()

        # Check for duplicate username
        for user in state.users.values():
            if user.username == username:
                raise ValueError(f"User '{username}' already exists")

        user = UserState(
            id=uuid.uuid4().hex,
            username=username,
            password_hash=self.hash_password(password),
            token=secrets.token_urlsafe(32),
            is_admin=is_admin,
        )
        state.users[user.id] = user
        self._state.save(state)
        return user

    def validate_token(self, token: str) -> UserState | None:
        """Look up a user by API token.

        Returns:
            The UserState if found, None otherwise.
        """
        state = self._state.load()
        for user in state.users.values():
            if user.token == token:
                return user
        return None

    def authenticate(self, username: str, password: str) -> UserState | None:
        """Authenticate with username and password.

        Returns:
            The UserState if credentials are valid, None otherwise.
        """
        state = self._state.load()
        for user in state.users.values():
            if user.username == username:
                if self.verify_password(password, user.password_hash):
                    return user
                return None
        return None
