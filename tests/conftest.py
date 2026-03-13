"""Shared test fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from kannix.app import create_app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for the FastAPI app (no deps, health only)."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
