"""Integration tests for /api/telegram endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# GET /api/telegram/status
# ---------------------------------------------------------------------------


class TestTelegramStatus:

    @pytest.mark.asyncio
    async def test_status_not_authenticated(self, client):
        with patch(
            "app.routers.telegram.tg_is_authenticated",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.get("/api/telegram/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False

    @pytest.mark.asyncio
    async def test_status_authenticated(self, client):
        with (
            patch(
                "app.routers.telegram.tg_is_authenticated",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.routers.telegram.get_settings",
            ) as mock_settings,
        ):
            mock_settings.return_value.telegram_api_id = "12345"
            mock_settings.return_value.telegram_api_hash = "abc"
            mock_settings.return_value.telegram_phone = "+1234567890"
            response = await client.get("/api/telegram/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True


# ---------------------------------------------------------------------------
# POST /api/telegram/auth/start
# ---------------------------------------------------------------------------


class TestTelegramAuthStart:

    @pytest.mark.asyncio
    async def test_auth_start_success(self, client):
        with patch(
            "app.routers.telegram.tg_start_auth",
            new_callable=AsyncMock,
            return_value={"ok": True, "phone_code_hash": "abc123"},
        ):
            response = await client.post(
                "/api/telegram/auth/start",
                json={"phone": "+1234567890"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_auth_start_failure(self, client):
        with patch(
            "app.routers.telegram.tg_start_auth",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network error"),
        ):
            response = await client.post(
                "/api/telegram/auth/start",
                json={"phone": "+1234567890"},
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/telegram/auth/verify
# ---------------------------------------------------------------------------


class TestTelegramAuthVerify:

    @pytest.mark.asyncio
    async def test_verify_success(self, client):
        with patch(
            "app.routers.telegram.tg_verify_auth",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.post(
                "/api/telegram/auth/verify",
                json={"code": "12345"},
            )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_verify_wrong_code(self, client):
        with patch(
            "app.routers.telegram.tg_verify_auth",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.post(
                "/api/telegram/auth/verify",
                json={"code": "00000"},
            )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/telegram/fetch
# ---------------------------------------------------------------------------


class TestTelegramFetch:

    @pytest.mark.asyncio
    async def test_fetch_success(self, client):
        fake_messages = [
            {
                "message_id": 1,
                "date": "2025-01-01T00:00:00",
                "media_type": "document",
                "filename": "report.pdf",
                "file_size": 1024,
                "caption": "Q4 report",
            },
            {
                "message_id": 2,
                "date": "2025-01-02T00:00:00",
                "media_type": "photo",
                "filename": None,
                "file_size": 512,
                "caption": None,
            },
        ]
        with (
            patch(
                "app.routers.telegram.tg_is_authenticated",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.routers.telegram.fetch_saved_messages",
                new_callable=AsyncMock,
                return_value=fake_messages,
            ),
        ):
            response = await client.post(
                "/api/telegram/fetch",
                json={"limit": 10},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["messages"]) == 2
        assert data["messages"][0]["message_id"] == 1

    @pytest.mark.asyncio
    async def test_fetch_not_authenticated(self, client):
        with patch(
            "app.routers.telegram.tg_is_authenticated",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.post(
                "/api/telegram/fetch",
                json={"limit": 10},
            )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/telegram/import  (SSE streaming)
# ---------------------------------------------------------------------------


class TestTelegramImport:

    @pytest.mark.asyncio
    async def test_import_streams_events(self, client):
        """Import should stream SSE events covering download and process phases."""
        mock_doc = {"id": "doc-1", "filename": "report.pdf"}

        with (
            patch(
                "app.routers.telegram.tg_is_authenticated",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.routers.telegram.download_message_media",
                new_callable=AsyncMock,
                return_value="/tmp/report.pdf",
            ),
            patch(
                "app.routers.telegram.ingest_document",
                new_callable=AsyncMock,
                return_value=mock_doc,
            ),
        ):
            async with client.stream(
                "POST",
                "/api/telegram/import",
                json={"message_ids": [1, 2]},
            ) as response:
                assert response.status_code == 200
                events = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

        # There should be events for both phases
        event_types = [e["type"] for e in events]
        assert "phase" in event_types
        assert "download" in event_types
        assert "process" in event_types
        assert "complete" in event_types

        # Verify download phase announced
        phase_events = [e for e in events if e["type"] == "phase"]
        assert any(e["phase"] == "downloading" for e in phase_events)
        assert any(e["phase"] == "processing" for e in phase_events)

        # Verify complete summary
        complete_evt = [e for e in events if e["type"] == "complete"][0]
        assert complete_evt["total"] == 2
        assert complete_evt["completed"] == 2
        assert complete_evt["errors"] == 0

    @pytest.mark.asyncio
    async def test_import_empty_message_ids(self, client):
        with patch(
            "app.routers.telegram.tg_is_authenticated",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.post(
                "/api/telegram/import",
                json={"message_ids": []},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_import_not_authenticated(self, client):
        with patch(
            "app.routers.telegram.tg_is_authenticated",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = await client.post(
                "/api/telegram/import",
                json={"message_ids": [1]},
            )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/telegram/import/stop
# ---------------------------------------------------------------------------


class TestTelegramImportStop:

    @pytest.mark.asyncio
    async def test_stop_import(self, client):
        response = await client.post("/api/telegram/import/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# GET /api/telegram/messages
# ---------------------------------------------------------------------------


class TestTelegramMessages:

    @pytest.mark.asyncio
    async def test_messages_returns_cached(self, client):
        """Without a prior fetch the cache is empty, so we get an empty list."""
        response = await client.get("/api/telegram/messages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["messages"], list)
        assert data["total"] >= 0
