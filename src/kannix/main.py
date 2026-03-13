"""Kannix application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

from kannix.app import create_app
from kannix.config import load_config
from kannix.state import StateManager


def main() -> None:
    """Run the Kannix server."""
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("kannix.json")
    state_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

    config = load_config(config_path)
    state_manager = StateManager(state_dir / "state.json")

    app = create_app(config=config, state_manager=state_manager)
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
