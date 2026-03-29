"""Integration tests for /api/backup endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# GET /api/backup/snapshots
# ---------------------------------------------------------------------------


class TestBackupSnapshots:

    @pytest.mark.asyncio
    async def test_snapshots_empty(self, client):
        with patch(
            "app.routers.backup.list_snapshots",
            return_value=[],
        ):
            response = await client.get("/api/backup/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert data["snapshots"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_snapshots_with_entries(self, client):
        fake_snapshots = [
            {"name": "snapshot_2025-01-01.tar", "size": 1024, "created": "2025-01-01T02:00:00"},
            {"name": "snapshot_2025-01-02.tar", "size": 2048, "created": "2025-01-02T02:00:00"},
        ]
        with patch(
            "app.routers.backup.list_snapshots",
            return_value=fake_snapshots,
        ):
            response = await client.get("/api/backup/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["snapshots"][0]["name"] == "snapshot_2025-01-01.tar"


# ---------------------------------------------------------------------------
# POST /api/backup/snapshot
# ---------------------------------------------------------------------------


class TestBackupCreate:

    @pytest.mark.asyncio
    async def test_create_snapshot_success(self, client):
        with patch(
            "app.routers.backup.trigger_snapshot",
            new_callable=AsyncMock,
            return_value={"status": "ok", "snapshot": "snapshot_2025-01-03.tar"},
        ):
            response = await client.post("/api/backup/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_create_snapshot_error(self, client):
        with patch(
            "app.routers.backup.trigger_snapshot",
            new_callable=AsyncMock,
            return_value={"status": "error", "message": "Qdrant unavailable"},
        ):
            response = await client.post("/api/backup/snapshot")
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_create_snapshot_exception(self, client):
        with patch(
            "app.routers.backup.trigger_snapshot",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            response = await client.post("/api/backup/snapshot")
        assert response.status_code == 500
