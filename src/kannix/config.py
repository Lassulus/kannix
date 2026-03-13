"""Configuration loading and validation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    from pathlib import Path


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080


class HooksConfig(BaseModel):
    """Lifecycle hook configuration."""

    on_create: str | None = None
    on_move: dict[str, str] = {}
    on_delete: str | None = None


class KannixConfig(BaseModel):
    """Root configuration model."""

    columns: list[str]
    hooks: HooksConfig = HooksConfig()
    server: ServerConfig = ServerConfig()

    @field_validator("columns")
    @classmethod
    def columns_must_be_nonempty(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("columns must not be empty")
        return v

    @field_validator("columns")
    @classmethod
    def columns_must_be_unique(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("columns must be unique")
        return v


def load_config(path: Path) -> KannixConfig:
    """Load and validate a Kannix config file.

    Args:
        path: Path to the JSON config file.

    Returns:
        Validated KannixConfig.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        ValueError: If the JSON is invalid or validation fails.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    text = path.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}") from e

    try:
        return KannixConfig.model_validate(data)
    except Exception as e:
        raise ValueError(str(e)) from e
