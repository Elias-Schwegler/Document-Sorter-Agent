"""Integration tests for rename-related /api/documents endpoints.

All Qdrant and service calls are mocked so tests run without Docker.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.dependencies as deps
from app.models.document import RenameSuggestions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_point(doc_id="doc-1", filename="test.txt", chunk_index=0, **extra):
    """Build a fake Qdrant point."""
    payload = {
        "doc_id": doc_id,
        "filename": filename,
        "original_filename": filename,
        "folder": "invoices",
        "file_type": "text",
        "file_size": 42,
        "page_count": 1,
        "ingested_at": "2025-01-01T00:00:00+00:00",
        "source": "upload",
        "chunk_index": chunk_index,
        "chunk_text": "sample chunk text",
        "full_text": "full document text for rename suggestions",
        "rename_suggestions": [],
        "rename_dismissed": False,
        **extra,
    }
    point = MagicMock()
    point.id = f"point-{doc_id}-{chunk_index}"
    point.payload = payload
    return point


@pytest.fixture
def _inject_qdrant(mock_qdrant):
    old = deps._qdrant_client
    deps._qdrant_client = mock_qdrant
    yield mock_qdrant
    deps._qdrant_client = old


# ---------------------------------------------------------------------------
# GET /api/documents/needs-rename
# ---------------------------------------------------------------------------


class TestNeedsRename:

    @pytest.mark.asyncio
    async def test_returns_docs_with_scan_names(self, client, mock_qdrant, _inject_qdrant):
        """Documents with scan-like names should appear in needs-rename list."""
        scan_point = _make_point("d1", "Scan_20250101_001.pdf")
        normal_point = _make_point("d2", "tax_return_2024.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([scan_point, normal_point], None))

        response = await client.get("/api/documents/needs-rename")

        assert response.status_code == 200
        data = response.json()
        doc_ids = [d["doc_id"] for d in data["documents"]]
        assert "d1" in doc_ids
        assert "d2" not in doc_ids

    @pytest.mark.asyncio
    async def test_excludes_dismissed_docs(self, client, mock_qdrant, _inject_qdrant):
        """Dismissed documents should not appear in needs-rename list."""
        dismissed = _make_point("d1", "IMG_20250101.jpg", rename_dismissed=True)
        mock_qdrant.scroll = AsyncMock(return_value=([dismissed], None))

        response = await client.get("/api/documents/needs-rename")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_includes_docs_with_stored_suggestions(self, client, mock_qdrant, _inject_qdrant):
        """Documents with stored rename_suggestions should appear even if name is normal."""
        point = _make_point("d1", "normal_name.pdf", rename_suggestions=["better_name.pdf"])
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        response = await client.get("/api/documents/needs-rename")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["documents"][0]["rename_suggestions"] == ["better_name.pdf"]


# ---------------------------------------------------------------------------
# POST /api/documents/{id}/dismiss-rename
# ---------------------------------------------------------------------------


class TestDismissRename:

    @pytest.mark.asyncio
    async def test_dismiss_sets_flag(self, client, mock_qdrant, _inject_qdrant):
        """Dismissing a document sets rename_dismissed=true in Qdrant."""
        point = _make_point("d1", "Scan_001.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))
        mock_qdrant.set_payload = AsyncMock()

        response = await client.post("/api/documents/d1/dismiss-rename")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_qdrant.set_payload.assert_called_once()
        call_payload = mock_qdrant.set_payload.call_args[1]["payload"]
        assert call_payload["rename_dismissed"] is True
        assert call_payload["rename_suggestions"] == []

    @pytest.mark.asyncio
    async def test_dismiss_not_found(self, client, mock_qdrant, _inject_qdrant):
        """Dismissing a non-existent document returns 404."""
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.post("/api/documents/ghost/dismiss-rename")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/documents/{id}/generate-suggestions
# ---------------------------------------------------------------------------


class TestGenerateSuggestions:

    @pytest.mark.asyncio
    async def test_returns_suggestions(self, client, mock_qdrant, _inject_qdrant):
        """generate-suggestions calls suggest_rename and returns suggestions."""
        point = _make_point("d1", "Scan_001.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))
        mock_qdrant.set_payload = AsyncMock()

        fake_result = RenameSuggestions(
            doc_id="d1",
            original_name="Scan_001.pdf",
            suggestions=["tax_return_2024.pdf", "income_statement.pdf"],
        )

        with (
            patch("app.services.renaming.suggest_rename", new_callable=AsyncMock, return_value=fake_result),
            patch("app.services.renaming.store_suggestions", new_callable=AsyncMock) as mock_store,
        ):
            response = await client.post("/api/documents/d1/generate-suggestions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) == 2
        assert "tax_return_2024.pdf" in data["suggestions"]
        # store_suggestions should have been called to persist
        mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, client, mock_qdrant, _inject_qdrant):
        """generate-suggestions returns 404 if document doesn't exist."""
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        # We need to import and patch at the router level
        with patch("app.routers.documents.suggest_rename", new_callable=AsyncMock):
            response = await client.post("/api/documents/ghost/generate-suggestions")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/documents/bulk-rename
# ---------------------------------------------------------------------------


class TestBulkRename:

    @pytest.mark.asyncio
    async def test_renames_multiple_docs(self, client, mock_qdrant, _inject_qdrant):
        """bulk-rename should rename each document and clear suggestions."""
        point = _make_point("d1", "Scan_001.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))
        mock_qdrant.set_payload = AsyncMock()

        with patch(
            "app.services.renaming.apply_rename",
            new_callable=AsyncMock,
            return_value="/sorted/invoices/tax_return.pdf",
        ):
            response = await client.post("/api/documents/bulk-rename", json={
                "items": [
                    {"doc_id": "d1", "new_name": "tax_return.pdf"},
                ]
            })

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "ok"
        assert data["results"][0]["new_name"] == "tax_return.pdf"

    @pytest.mark.asyncio
    async def test_bulk_rename_handles_errors(self, client, mock_qdrant, _inject_qdrant):
        """bulk-rename should report errors per document without failing entirely."""
        with patch(
            "app.services.renaming.apply_rename",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError("File not found"),
        ):
            response = await client.post("/api/documents/bulk-rename", json={
                "items": [
                    {"doc_id": "d1", "new_name": "new_name.pdf"},
                ]
            })

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# POST /api/documents/{id}/rename (apply=true clears suggestions)
# ---------------------------------------------------------------------------


class TestRenameApply:

    @pytest.mark.asyncio
    async def test_rename_clears_suggestions(self, client, mock_qdrant, _inject_qdrant):
        """Applying a rename should clear rename_suggestions in Qdrant."""
        point = _make_point("d1", "Scan_001.pdf", file_path="/fake/Scan_001.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))
        mock_qdrant.set_payload = AsyncMock()

        with patch(
            "app.routers.documents.apply_rename",
            new_callable=AsyncMock,
            return_value="/sorted/invoices/tax_return.pdf",
        ):
            response = await client.post("/api/documents/d1/rename", json={
                "suggested_name": "tax_return.pdf",
                "apply": True,
            })

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] is True
        # Verify set_payload was called with empty suggestions
        calls = mock_qdrant.set_payload.call_args_list
        found_clear = any(
            call[1].get("payload", {}).get("rename_suggestions") == []
            for call in calls
        )
        assert found_clear, "rename_suggestions should have been cleared"
