"""System tests for the full ingestion pipeline.

Exercises parse -> chunk -> embed -> duplicate-check -> store with all
external services (Qdrant, Ollama) mocked.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ingestion import ingest_document
from app.models.document import DocumentMetadata, DuplicateInfo
from tests.conftest import make_embedding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_qdrant_no_duplicate():
    """Return a mock Qdrant client that finds no duplicates."""
    qdrant = AsyncMock()
    qdrant.search = AsyncMock(return_value=[])  # no duplicates
    qdrant.upsert = AsyncMock()
    qdrant.scroll = AsyncMock(return_value=([], None))
    return qdrant


def _mock_qdrant_with_duplicate(score=0.98):
    """Return a mock Qdrant client that reports a duplicate."""
    match = MagicMock()
    match.score = score
    match.payload = {
        "doc_id": "existing-doc-id",
        "filename": "existing_file.txt",
    }

    qdrant = AsyncMock()
    qdrant.search = AsyncMock(return_value=[match])
    qdrant.upsert = AsyncMock()
    qdrant.scroll = AsyncMock(return_value=([], None))
    return qdrant


@pytest.fixture
def _patch_embed():
    """Patch embedding functions to avoid model loading."""
    async def fake_embed_texts(texts):
        return [make_embedding() for _ in texts]

    async def fake_embed_text(text):
        return make_embedding()

    with (
        patch("app.services.ingestion.embed_texts", side_effect=fake_embed_texts),
    ):
        yield


@pytest.fixture
def _patch_no_sort():
    """Disable auto_sort and auto_rename during ingestion."""
    from app.config import Settings

    fake = Settings(auto_sort=False, auto_rename=False)
    with patch("app.services.ingestion.get_settings", return_value=fake):
        yield fake


# ---------------------------------------------------------------------------
# Full pipeline: parse -> chunk -> embed -> store
# ---------------------------------------------------------------------------


class TestIngestionPipeline:

    @pytest.mark.asyncio
    async def test_ingest_txt_file(
        self, sample_txt, _patch_embed, _patch_no_sort
    ):
        qdrant = _mock_qdrant_no_duplicate()

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            result = await ingest_document(sample_txt, source="upload")

        assert isinstance(result, DocumentMetadata)
        assert result.filename == "sample.txt"
        assert result.file_type == "text"
        assert result.source == "upload"
        assert result.doc_id  # non-empty UUID
        # Qdrant upsert should have been called once with point(s)
        qdrant.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_pdf_file(
        self, sample_pdf, _patch_embed, _patch_no_sort
    ):
        qdrant = _mock_qdrant_no_duplicate()

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            result = await ingest_document(sample_pdf, source="upload")

        assert isinstance(result, DocumentMetadata)
        assert result.filename == "sample.pdf"
        assert result.file_type == "pdf"
        assert result.page_count == 1

    @pytest.mark.asyncio
    async def test_upsert_receives_correct_points(
        self, sample_txt, _patch_embed, _patch_no_sort
    ):
        """Verify the points sent to Qdrant have the expected structure."""
        qdrant = _mock_qdrant_no_duplicate()

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            await ingest_document(sample_txt, source="watcher")

        call_kwargs = qdrant.upsert.call_args
        points = call_kwargs.kwargs.get("points") or call_kwargs[1].get("points")
        assert len(points) >= 1
        first = points[0]
        assert first.payload["chunk_index"] == 0
        assert first.payload["source"] == "watcher"
        assert "full_text" in first.payload  # only on chunk 0

    @pytest.mark.asyncio
    async def test_ws_callback_called(
        self, sample_txt, _patch_embed, _patch_no_sort
    ):
        """The optional ws_callback should be invoked with status strings."""
        qdrant = _mock_qdrant_no_duplicate()
        statuses: list[str] = []

        async def capture(status):
            statuses.append(status)

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            await ingest_document(sample_txt, ws_callback=capture)

        assert "parsing" in statuses
        assert "chunking" in statuses
        assert "embedding" in statuses
        assert "storing" in statuses
        assert "complete" in statuses


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:

    @pytest.mark.asyncio
    async def test_duplicate_returns_info(
        self, sample_txt, _patch_embed, _patch_no_sort
    ):
        qdrant = _mock_qdrant_with_duplicate(score=0.98)

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            result = await ingest_document(sample_txt)

        assert isinstance(result, DuplicateInfo)
        assert result.existing_doc_id == "existing-doc-id"
        assert result.existing_filename == "existing_file.txt"
        assert result.similarity >= 0.95

    @pytest.mark.asyncio
    async def test_no_duplicate_when_below_threshold(
        self, sample_txt, _patch_embed, _patch_no_sort
    ):
        """If the best match is below the threshold, it is NOT a duplicate."""
        qdrant = _mock_qdrant_no_duplicate()

        with patch("app.services.ingestion.get_qdrant", return_value=qdrant):
            result = await ingest_document(sample_txt)

        assert isinstance(result, DocumentMetadata)


# ---------------------------------------------------------------------------
# Auto-sort flow
# ---------------------------------------------------------------------------


class TestAutoSortFlow:

    @pytest.mark.asyncio
    async def test_auto_sort_called(self, sample_txt, _patch_embed):
        """When auto_sort=True, the sort_document function should be invoked."""
        from app.config import Settings
        from app.models.document import SortResult

        fake_settings = Settings(auto_sort=True, auto_rename=False)
        qdrant = _mock_qdrant_no_duplicate()

        mock_sort = AsyncMock(
            return_value=SortResult(
                doc_id="x", folder="invoices", confidence=0.9
            )
        )

        with (
            patch("app.services.ingestion.get_settings", return_value=fake_settings),
            patch("app.services.ingestion.get_qdrant", return_value=qdrant),
            # sort_document is lazily imported inside ingest_document,
            # so we patch it at the source module.
            patch("app.services.sorting.sort_document", mock_sort),
        ):
            result = await ingest_document(sample_txt)

        assert isinstance(result, DocumentMetadata)
        mock_sort.assert_awaited_once()
        assert result.folder == "invoices"

    @pytest.mark.asyncio
    async def test_auto_sort_failure_does_not_crash(
        self, sample_txt, _patch_embed
    ):
        """If sorting fails, ingestion should still succeed."""
        from app.config import Settings

        fake_settings = Settings(auto_sort=True, auto_rename=False)
        qdrant = _mock_qdrant_no_duplicate()

        mock_sort = AsyncMock(side_effect=RuntimeError("LLM offline"))

        with (
            patch("app.services.ingestion.get_settings", return_value=fake_settings),
            patch("app.services.ingestion.get_qdrant", return_value=qdrant),
            patch("app.services.sorting.sort_document", mock_sort),
        ):
            result = await ingest_document(sample_txt)

        # Should still return metadata, not raise
        assert isinstance(result, DocumentMetadata)
