"""Integration tests for /api/settings endpoints."""

from unittest.mock import patch

import pytest

from app.config import Settings


@pytest.fixture
def _patch_settings(client):
    """Provide a fresh Settings instance for each test.

    Depends on ``client`` to ensure app modules are imported first.
    """
    fake = Settings()
    with (
        patch("app.routers.settings.get_settings", return_value=fake),
        patch("app.routers.settings.is_bot_running", return_value=False),
    ):
        yield fake


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------


class TestGetSettings:

    @pytest.mark.asyncio
    async def test_get_settings(self, client, _patch_settings):
        response = await client.get("/api/settings")
        assert response.status_code == 200
        body = response.json()
        # Spot-check a few known keys
        assert "auto_sort" in body
        assert "chunk_size" in body
        assert "ollama_mode" in body
        assert "instance_name" in body

    @pytest.mark.asyncio
    async def test_get_settings_values(self, client, _patch_settings):
        response = await client.get("/api/settings")
        body = response.json()
        assert body["chunk_size"] == 1500
        assert body["auto_sort"] is True


# ---------------------------------------------------------------------------
# PUT /api/settings
# ---------------------------------------------------------------------------


class TestUpdateSettings:

    @pytest.mark.asyncio
    async def test_update_single_field(self, client, _patch_settings):
        response = await client.put(
            "/api/settings", json={"chunk_size": 2000}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["updated"]["chunk_size"] == 2000

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client, _patch_settings):
        response = await client.put(
            "/api/settings",
            json={"auto_sort": False, "duplicate_threshold": 0.8},
        )
        assert response.status_code == 200
        updated = response.json()["updated"]
        assert updated["auto_sort"] is False
        assert updated["duplicate_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_update_no_fields(self, client, _patch_settings):
        response = await client.put("/api/settings", json={})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_persists_in_runtime(self, client, _patch_settings):
        """After update, GET should reflect the new values."""
        await client.put("/api/settings", json={"chunk_size": 999})
        response = await client.get("/api/settings")
        assert response.json()["chunk_size"] == 999
