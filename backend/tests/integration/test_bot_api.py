"""Integration tests for /api/bot endpoints."""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# GET /api/bot/status
# ---------------------------------------------------------------------------


class TestBotStatus:

    @pytest.mark.asyncio
    async def test_status_not_running(self, client):
        with patch(
            "app.routers.bot.is_bot_running",
            return_value=False,
        ):
            response = await client.get("/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False
        assert "instance_name" in data
        assert "token_configured" in data

    @pytest.mark.asyncio
    async def test_status_running(self, client):
        with patch(
            "app.routers.bot.is_bot_running",
            return_value=True,
        ):
            response = await client.get("/api/bot/status")
        assert response.status_code == 200
        assert response.json()["running"] is True


# ---------------------------------------------------------------------------
# GET /api/bot/instances
# ---------------------------------------------------------------------------


class TestBotInstances:

    @pytest.mark.asyncio
    async def test_instances_empty(self, client):
        with patch(
            "app.routers.bot.get_instances",
            return_value={},
        ):
            response = await client.get("/api/bot/instances")
        assert response.status_code == 200
        data = response.json()
        assert data["instances"] == []

    @pytest.mark.asyncio
    async def test_instances_with_entries(self, client):
        fake_instances = {
            "Default": {"base_url": "http://localhost:8000", "last_seen": "2025-01-01T00:00:00"},
            "Remote": {"base_url": "http://remote:8000", "last_seen": "2025-01-02T00:00:00"},
        }
        with patch(
            "app.routers.bot.get_instances",
            return_value=fake_instances,
        ):
            response = await client.get("/api/bot/instances")
        assert response.status_code == 200
        instances = response.json()["instances"]
        assert len(instances) == 2
        names = [i["instance_name"] for i in instances]
        assert "Default" in names
        assert "Remote" in names


# ---------------------------------------------------------------------------
# POST /api/bot/register-instance
# ---------------------------------------------------------------------------


class TestBotRegisterInstance:

    @pytest.mark.asyncio
    async def test_register_instance(self, client):
        with patch(
            "app.routers.bot.register_instance",
        ) as mock_reg:
            response = await client.post(
                "/api/bot/register-instance",
                json={
                    "instance_name": "TestInstance",
                    "base_url": "http://test:8000",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["instance_name"] == "TestInstance"
        mock_reg.assert_called_once_with("TestInstance", "http://test:8000")
