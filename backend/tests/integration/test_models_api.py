"""Integration tests for /api/models endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# GET /api/models
# ---------------------------------------------------------------------------


class TestListModels:

    @pytest.mark.asyncio
    async def test_list_models(self, client):
        fake_models = [
            {"name": "qwen3.5:4b", "size": 2_500_000_000, "modified_at": "2025-01-01T00:00:00"},
            {"name": "llama3:8b", "size": 4_000_000_000, "modified_at": "2025-01-02T00:00:00"},
        ]
        with patch(
            "app.routers.models.list_models",
            new_callable=AsyncMock,
            return_value=fake_models,
        ):
            response = await client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "qwen3.5:4b"

    @pytest.mark.asyncio
    async def test_list_models_empty(self, client):
        with patch(
            "app.routers.models.list_models",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = await client.get("/api/models")
        assert response.status_code == 200
        assert response.json()["models"] == []

    @pytest.mark.asyncio
    async def test_list_models_error(self, client):
        with patch(
            "app.routers.models.list_models",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Ollama unreachable"),
        ):
            response = await client.get("/api/models")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/models/active
# ---------------------------------------------------------------------------


class TestGetActiveModels:

    @pytest.mark.asyncio
    async def test_get_active_models(self, client):
        response = await client.get("/api/models/active")
        assert response.status_code == 200
        data = response.json()
        assert "agent_model" in data
        assert "embedding_model" in data


# ---------------------------------------------------------------------------
# PUT /api/models/active
# ---------------------------------------------------------------------------


class TestSetActiveModel:

    @pytest.mark.asyncio
    async def test_update_agent_model(self, client):
        response = await client.put(
            "/api/models/active",
            json={"agent_model": "llama3:8b"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["updated"]["agent_model"] == "llama3:8b"

    @pytest.mark.asyncio
    async def test_update_embedding_model(self, client):
        response = await client.put(
            "/api/models/active",
            json={"embedding_model": "nomic-embed-text"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated"]["embedding_model"] == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_update_both_models(self, client):
        response = await client.put(
            "/api/models/active",
            json={"agent_model": "llama3:8b", "embedding_model": "nomic-embed-text"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "agent_model" in data["updated"]
        assert "embedding_model" in data["updated"]

    @pytest.mark.asyncio
    async def test_update_no_fields(self, client):
        response = await client.put(
            "/api/models/active",
            json={},
        )
        assert response.status_code == 400
