"""Integration tests for folder approval endpoints."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.dependencies as deps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_point(doc_id="doc-1", filename="test.pdf", chunk_index=0, **extra):
    payload = {
        "doc_id": doc_id,
        "filename": filename,
        "original_filename": filename,
        "folder": "_review",
        "file_type": "pdf",
        "file_size": 1024,
        "page_count": 1,
        "ingested_at": "2025-01-01T00:00:00+00:00",
        "source": "upload",
        "chunk_index": chunk_index,
        "chunk_text": "chunk",
        "full_text": "full text content",
        "pending_folder": "",
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
# GET /api/documents/pending-folders
# ---------------------------------------------------------------------------


class TestPendingFolders:

    @pytest.mark.asyncio
    async def test_returns_docs_with_pending_folder(self, client, mock_qdrant, _inject_qdrant):
        """Documents with a non-empty pending_folder should be listed."""
        pending = _make_point("d1", "invoice.pdf", pending_folder="new_invoices")
        no_pending = _make_point("d2", "report.pdf", pending_folder="")
        mock_qdrant.scroll = AsyncMock(return_value=([pending, no_pending], None))

        response = await client.get("/api/documents/pending-folders")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["documents"][0]["doc_id"] == "d1"
        assert data["documents"][0]["proposed_folder"] == "new_invoices"

    @pytest.mark.asyncio
    async def test_empty_when_no_pending(self, client, mock_qdrant, _inject_qdrant):
        """When no documents have pending folders, return empty list."""
        point = _make_point("d1", "report.pdf", pending_folder="")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        response = await client.get("/api/documents/pending-folders")

        assert response.status_code == 200
        assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# POST /api/documents/approve-folder
# ---------------------------------------------------------------------------


class TestApproveFolder:

    @pytest.mark.asyncio
    async def test_approve_creates_folder_and_moves_file(self, client, mock_qdrant, _inject_qdrant, temp_dir):
        """Approving a folder should create it, move the file, and update Qdrant."""
        src_file = temp_dir / "_review" / "invoice.pdf"
        src_file.parent.mkdir(parents=True)
        src_file.write_bytes(b"%PDF-content")

        point = _make_point("d1", "invoice.pdf", file_path=str(src_file), pending_folder="new_invoices")
        chunk_point = _make_point("d1", "invoice.pdf", chunk_index=1)

        # First scroll: find the doc; Second scroll: find all chunks
        mock_qdrant.scroll = AsyncMock(
            side_effect=[
                ([point], None),
                ([point, chunk_point], None),
            ]
        )
        mock_qdrant.set_payload = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"

        new_path = str(temp_dir / "new_invoices" / "invoice.pdf")

        with (
            patch("app.routers.documents.get_settings", return_value=mock_settings),
            patch("app.routers.documents.move_file", return_value=new_path),
        ):
            response = await client.post("/api/documents/approve-folder", json={
                "doc_id": "d1",
                "approved_folder": "new_invoices",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["folder"] == "new_invoices"

        # Folder should have been created (os.makedirs in the handler)
        assert os.path.isdir(str(temp_dir / "new_invoices"))

    @pytest.mark.asyncio
    async def test_approve_not_found(self, client, mock_qdrant, _inject_qdrant):
        """Approving a non-existent document returns 404."""
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.post("/api/documents/approve-folder", json={
            "doc_id": "ghost",
            "approved_folder": "invoices",
        })

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_empty_folder_name(self, client, mock_qdrant, _inject_qdrant):
        """Approving with an empty folder name returns 400."""
        point = _make_point("d1", "invoice.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        response = await client.post("/api/documents/approve-folder", json={
            "doc_id": "d1",
            "approved_folder": "",
        })

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/documents/reject-folder
# ---------------------------------------------------------------------------


class TestRejectFolder:

    @pytest.mark.asyncio
    async def test_reject_clears_pending_folder(self, client, mock_qdrant, _inject_qdrant):
        """Rejecting a folder clears the pending_folder field in Qdrant."""
        point = _make_point("d1", "invoice.pdf", pending_folder="new_invoices")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))
        mock_qdrant.set_payload = AsyncMock()

        response = await client.post("/api/documents/reject-folder", json={
            "doc_id": "d1",
            "approved_folder": "",  # required by model but unused
        })

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_qdrant.set_payload.assert_called_once()
        call_payload = mock_qdrant.set_payload.call_args[1]["payload"]
        assert call_payload["pending_folder"] == ""

    @pytest.mark.asyncio
    async def test_reject_no_points_still_ok(self, client, mock_qdrant, _inject_qdrant):
        """Rejecting when no points found still returns ok (no-op)."""
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.post("/api/documents/reject-folder", json={
            "doc_id": "ghost",
            "approved_folder": "",
        })

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
