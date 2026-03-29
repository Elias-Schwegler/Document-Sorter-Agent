"""Integration tests for /api/documents endpoints.

All Qdrant and Ollama calls are mocked so tests run without Docker.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.dependencies as deps
from tests.conftest import make_embedding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_point(doc_id="doc-1", filename="test.txt", chunk_index=0, **extra):
    """Build a fake Qdrant point (MagicMock)."""
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
        "chunk_text": "sample chunk",
        "full_text": "full document text here",
        **extra,
    }
    point = MagicMock()
    point.id = f"point-{doc_id}-{chunk_index}"
    point.payload = payload
    return point


@pytest.fixture
def _inject_qdrant(mock_qdrant):
    """Inject a mock qdrant client into the global singleton so that
    ``get_qdrant()`` returns it without making a real connection."""
    old = deps._qdrant_client
    deps._qdrant_client = mock_qdrant
    yield mock_qdrant
    deps._qdrant_client = old


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUploadDocument:

    @pytest.mark.asyncio
    async def test_upload_txt_file(self, client, mock_embed, _inject_qdrant):
        """POST /api/documents/upload with a simple .txt file."""
        from app.models.document import DocumentMetadata

        mock_ingest = AsyncMock(return_value=DocumentMetadata(
            doc_id="abc-123",
            filename="hello.txt",
            original_filename="hello.txt",
            folder="misc",
            file_type="text",
            file_size=13,
            page_count=1,
            ingested_at="2025-01-01T00:00:00+00:00",
            source="upload",
        ))

        with patch("app.routers.documents.ingest_document", mock_ingest):
            content = b"Hello, world!"
            response = await client.post(
                "/api/documents/upload",
                files=[("files", ("hello.txt", io.BytesIO(content), "text/plain"))],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "ingested"
        assert data["results"][0]["doc_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_upload_unsupported_extension(self, client):
        """Unsupported file types should be rejected."""
        content = b"binary data"
        response = await client.post(
            "/api/documents/upload",
            files=[("files", ("archive.zip", io.BytesIO(content), "application/zip"))],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["status"] == "rejected"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestListDocuments:

    @pytest.mark.asyncio
    async def test_list_documents(self, client, mock_qdrant, _inject_qdrant):
        points = [_make_point("d1", "a.txt"), _make_point("d2", "b.pdf")]
        mock_qdrant.scroll = AsyncMock(return_value=(points, None))

        response = await client.get("/api/documents")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        filenames = [d["filename"] for d in body["documents"]]
        assert "a.txt" in filenames
        assert "b.pdf" in filenames

    @pytest.mark.asyncio
    async def test_list_empty(self, client, mock_qdrant, _inject_qdrant):
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.get("/api/documents")

        assert response.status_code == 200
        assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# Get detail
# ---------------------------------------------------------------------------


class TestGetDocument:

    @pytest.mark.asyncio
    async def test_get_existing(self, client, mock_qdrant, _inject_qdrant):
        point = _make_point("doc-1", "report.pdf")
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        response = await client.get("/api/documents/doc-1")

        assert response.status_code == 200
        assert response.json()["doc_id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client, mock_qdrant, _inject_qdrant):
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.get("/api/documents/nonexistent")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteDocument:

    @pytest.mark.asyncio
    async def test_delete_existing(self, client, mock_qdrant, _inject_qdrant):
        points = [
            _make_point("doc-1", "f.txt", 0),
            _make_point("doc-1", "f.txt", 1),
        ]
        mock_qdrant.scroll = AsyncMock(return_value=(points, None))
        mock_qdrant.delete = AsyncMock()

        response = await client.delete("/api/documents/doc-1")

        assert response.status_code == 200
        body = response.json()
        assert body["chunks_deleted"] == 2

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client, mock_qdrant, _inject_qdrant):
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.delete("/api/documents/ghost")

        assert response.status_code == 404
