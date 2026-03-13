"""Kannix application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from kannix.app import create_app
from kannix.config import load_config
from kannix.state import StateManager

if TYPE_CHECKING:
    from fastapi import FastAPI


def _get_config_and_state() -> tuple[Path, Path]:
    """Get config path and state dir from args or env."""
    config_path = Path(
        os.environ.get("KANNIX_CONFIG", sys.argv[1] if len(sys.argv) > 1 else "kannix.json")
    )
    state_dir = Path(os.environ.get("KANNIX_STATE_DIR", sys.argv[2] if len(sys.argv) > 2 else "."))
    return config_path, state_dir


def create_dev_app() -> FastAPI:
    """App factory for uvicorn --reload (reads config from env vars only)."""
    config_path = Path(os.environ.get("KANNIX_CONFIG", "dev-config.json"))
    state_dir = Path(os.environ.get("KANNIX_STATE_DIR", "/tmp/kannix-dev"))
    state_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    state_manager = StateManager(state_dir / "state.json")
    return create_app(config=config, state_manager=state_manager)


def main() -> None:
    """Run the Kannix server."""
    config_path, state_dir = _get_config_and_state()
    config = load_config(config_path)
    state_manager = StateManager(state_dir / "state.json")

    app = create_app(config=config, state_manager=state_manager)
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
