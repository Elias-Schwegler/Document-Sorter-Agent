"""Integration tests for POST /api/documents/reconcile."""

from unittest.mock import AsyncMock, patch

import pytest

import app.dependencies as deps


@pytest.fixture
def _inject_qdrant(mock_qdrant):
    old = deps._qdrant_client
    deps._qdrant_client = mock_qdrant
    yield mock_qdrant
    deps._qdrant_client = old


class TestReconcileApi:

    @pytest.mark.asyncio
    async def test_reconcile_returns_summary(self, client, _inject_qdrant):
        """POST /api/documents/reconcile returns ok/moved/deleted/updated counts."""
        fake_summary = {"ok": 5, "moved": 1, "deleted": 2, "updated": 1}

        with patch(
            "app.services.reconcile.reconcile_documents",
            new_callable=AsyncMock,
            return_value=fake_summary,
        ):
            response = await client.post("/api/documents/reconcile")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == 5
        assert data["moved"] == 1
        assert data["deleted"] == 2
        assert data["updated"] == 1

    @pytest.mark.asyncio
    async def test_reconcile_empty_collection(self, client, _inject_qdrant):
        """Reconcile on an empty collection returns all zeros."""
        with patch(
            "app.services.reconcile.reconcile_documents",
            new_callable=AsyncMock,
            return_value={"ok": 0, "moved": 0, "deleted": 0, "updated": 0},
        ):
            response = await client.post("/api/documents/reconcile")

        assert response.status_code == 200
        data = response.json()
        assert data == {"ok": 0, "moved": 0, "deleted": 0, "updated": 0}
