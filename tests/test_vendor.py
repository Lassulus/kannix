"""Tests for vendored static files (diff2html)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from httpx import ASGITransport, AsyncClient

from kannix.app import create_app
from kannix.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


async def _make_client(tmp_path: Path) -> AsyncClient:
    config_path = tmp_path / "kannix.json"
    config_path.write_text(json.dumps({"columns": ["Todo"]}))
    from kannix.config import load_config

    config = load_config(config_path)
    sm = StateManager(tmp_path / "state.json")
    app = create_app(config=config, state_manager=sm)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_diff2html_css_served(tmp_path: Path) -> None:
    """diff2html CSS should be served at /static/vendor/diff2html.min.css."""
    client = await _make_client(tmp_path)
    async with client:
        resp = await client.get("/static/vendor/diff2html.min.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]


async def test_diff2html_js_served(tmp_path: Path) -> None:
    """diff2html JS should be served at /static/vendor/diff2html-ui.min.js."""
    client = await _make_client(tmp_path)
    async with client:
        resp = await client.get("/static/vendor/diff2html-ui.min.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers["content-type"]
