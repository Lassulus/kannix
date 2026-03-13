"""Tests for auth module: password hashing, user management, tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kannix.auth import AuthManager
from kannix.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def state_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "state.json")


@pytest.fixture
def auth(state_manager: StateManager) -> AuthManager:
    return AuthManager(state_manager)


def test_hash_password_returns_different_from_input(auth: AuthManager):
    hashed = auth.hash_password("secret123")
    assert hashed != "secret123"
    assert len(hashed) > 20


def test_verify_password_correct(auth: AuthManager):
    hashed = auth.hash_password("mypassword")
    assert auth.verify_password("mypassword", hashed) is True


def test_verify_password_incorrect(auth: AuthManager):
    hashed = auth.hash_password("mypassword")
    assert auth.verify_password("wrongpassword", hashed) is False


def test_create_user(auth: AuthManager):
    user = auth.create_user("alice", "pass123", is_admin=False)
    assert user.username == "alice"
    assert user.id != ""
    assert user.token != ""
    assert user.is_admin is False
    assert user.password_hash != "pass123"


def test_create_admin_user(auth: AuthManager):
    user = auth.create_user("admin", "adminpass", is_admin=True)
    assert user.is_admin is True


def test_create_user_persists_to_state(auth: AuthManager, state_manager: StateManager):
    auth.create_user("bob", "pass456", is_admin=False)
    state = state_manager.load()
    assert len(state.users) == 1
    user = next(iter(state.users.values()))
    assert user.username == "bob"


def test_duplicate_username_rejected(auth: AuthManager):
    auth.create_user("alice", "pass1", is_admin=False)
    with pytest.raises(ValueError, match="already exists"):
        auth.create_user("alice", "pass2", is_admin=False)


def test_token_generation_is_unique(auth: AuthManager):
    u1 = auth.create_user("user1", "pass1", is_admin=False)
    u2 = auth.create_user("user2", "pass2", is_admin=False)
    assert u1.token != u2.token


def test_validate_token_returns_user(auth: AuthManager):
    user = auth.create_user("alice", "pass", is_admin=False)
    found = auth.validate_token(user.token)
    assert found is not None
    assert found.username == "alice"


def test_validate_invalid_token_returns_none(auth: AuthManager):
    auth.create_user("alice", "pass", is_admin=False)
    assert auth.validate_token("bogus-token") is None


def test_authenticate_valid_credentials(auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    user = auth.authenticate("alice", "secret")
    assert user is not None
    assert user.username == "alice"


def test_authenticate_wrong_password(auth: AuthManager):
    auth.create_user("alice", "secret", is_admin=False)
    assert auth.authenticate("alice", "wrong") is None


def test_authenticate_unknown_user(auth: AuthManager):
    assert auth.authenticate("nobody", "pass") is None
