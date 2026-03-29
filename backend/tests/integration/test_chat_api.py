"""Integration tests for /api/chat endpoints."""

from unittest.mock import patch

import pytest

from app.services.rag import _conversation_history, clear_history
from app.models.chat import ChatMessage


@pytest.fixture(autouse=True)
def _clear_history():
    """Ensure chat history is empty before and after each test."""
    clear_history()
    yield
    clear_history()


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------


class TestChatHistory:

    @pytest.mark.asyncio
    async def test_empty_history(self, client):
        response = await client.get("/api/chat/history")
        assert response.status_code == 200
        assert response.json()["messages"] == []

    @pytest.mark.asyncio
    async def test_history_after_messages(self, client):
        """Manually inject messages and verify the GET endpoint returns them."""
        _conversation_history.append(
            ChatMessage(role="user", content="Hello")
        )
        _conversation_history.append(
            ChatMessage(role="assistant", content="Hi there!")
        )
        response = await client.get("/api/chat/history")
        assert response.status_code == 200
        msgs = response.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# DELETE /api/chat/history
# ---------------------------------------------------------------------------


class TestClearChatHistory:

    @pytest.mark.asyncio
    async def test_clear_history(self, client):
        _conversation_history.append(
            ChatMessage(role="user", content="test")
        )
        response = await client.delete("/api/chat/history")
        assert response.status_code == 200

        # Verify it is actually cleared
        get_resp = await client.get("/api/chat/history")
        assert get_resp.json()["messages"] == []

    @pytest.mark.asyncio
    async def test_clear_already_empty(self, client):
        """Clearing an empty history should still succeed."""
        response = await client.delete("/api/chat/history")
        assert response.status_code == 200
