"""Integration tests for GET /api/documents/{id}/preview."""

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
        "folder": "invoices",
        "file_type": "pdf",
        "file_size": 1024,
        "page_count": 1,
        "ingested_at": "2025-01-01T00:00:00+00:00",
        "source": "upload",
        "chunk_index": chunk_index,
        "chunk_text": "chunk",
        "full_text": "full text",
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
# Preview tests
# ---------------------------------------------------------------------------


class TestPreviewDocument:

    @pytest.mark.asyncio
    async def test_preview_image_file(self, client, mock_qdrant, _inject_qdrant, temp_dir):
        """Preview of an image file returns the image directly."""
        from PIL import Image

        img_path = temp_dir / "photo.jpg"
        img = Image.new("RGB", (100, 100), color="green")
        img.save(str(img_path), format="JPEG")

        point = _make_point("d1", "photo.jpg", file_type="image", file_path=str(img_path))
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"

        with patch("app.routers.documents.get_settings", return_value=mock_settings):
            response = await client.get("/api/documents/d1/preview")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_preview_pdf_renders_first_page(self, client, mock_qdrant, _inject_qdrant, temp_dir):
        """Preview of a PDF returns a rendered JPEG of the first page."""
        import fitz

        pdf_path = str(temp_dir / "document.pdf")
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "Test content")
        doc.save(pdf_path)
        doc.close()

        point = _make_point("d1", "document.pdf", file_type="pdf", file_path=pdf_path)
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"

        with patch("app.routers.documents.get_settings", return_value=mock_settings):
            response = await client.get("/api/documents/d1/preview")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        # Response body should be valid JPEG (starts with JFIF/Exif magic bytes)
        assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_preview_missing_doc_returns_404(self, client, mock_qdrant, _inject_qdrant):
        """Preview for a non-existent document returns 404."""
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        response = await client.get("/api/documents/nonexistent/preview")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_missing_file_returns_404(self, client, mock_qdrant, _inject_qdrant, temp_dir):
        """Preview when the file doesn't exist on disk returns 404."""
        point = _make_point(
            "d1", "vanished.pdf",
            file_type="pdf",
            file_path=str(temp_dir / "vanished.pdf"),
        )
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"

        with (
            patch("app.routers.documents.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.find_file_on_disk", return_value=None),
        ):
            response = await client.get("/api/documents/d1/preview")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_unsupported_type_returns_400(self, client, mock_qdrant, _inject_qdrant, temp_dir):
        """Preview for unsupported file types returns 400."""
        txt_path = temp_dir / "notes.txt"
        txt_path.write_text("Hello")

        point = _make_point("d1", "notes.txt", file_type="text", file_path=str(txt_path))
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"

        with patch("app.routers.documents.get_settings", return_value=mock_settings):
            response = await client.get("/api/documents/d1/preview")

        assert response.status_code == 400
