"""Unit tests for the vector-based sorting context in app.services.sorting."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_similar_hit(filename: str, folder: str, score: float = 0.8):
    """Build a fake Qdrant scored point for query_points results."""
    hit = MagicMock()
    hit.payload = {"filename": filename, "folder": folder}
    hit.score = score
    return hit


def _make_query_result(hits):
    """Wrap hits in a result object with a .points attribute."""
    result = MagicMock()
    result.points = hits
    return result


# ---------------------------------------------------------------------------
# sort_document — similar-document context
# ---------------------------------------------------------------------------


class TestSortingContext:

    @pytest.mark.asyncio
    async def test_similar_docs_included_in_prompt(self, temp_dir):
        """When similar documents exist in Qdrant, the sort prompt includes examples."""
        from app.services.sorting import sort_document

        similar_hits = [
            _make_similar_hit("invoice_2024.pdf", "invoices"),
            _make_similar_hit("receipt_amazon.pdf", "invoices"),
        ]

        # Mock Qdrant
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=_make_query_result(similar_hits))
        # scroll returns a point for file path lookup
        file_point = MagicMock()
        file_point.id = "pt-1"
        file_point.payload = {"file_path": str(temp_dir / "doc.pdf")}
        mock_qdrant.scroll = AsyncMock(return_value=([file_point], None))
        mock_qdrant.set_payload = AsyncMock()

        # Mock HTTP client (Ollama API)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"folder": "invoices", "confidence": 0.9})}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"
        mock_settings.sort_confidence_threshold = 0.6

        # Create a folder so it's considered "existing"
        (temp_dir / "invoices").mkdir()

        with (
            patch("app.services.sorting.get_settings", return_value=mock_settings),
            patch("app.services.sorting.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
            patch("app.services.sorting.get_http_client", new_callable=AsyncMock, return_value=mock_http),
            patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.services.sorting.move_file", return_value=str(temp_dir / "invoices" / "doc.pdf")),
            patch("os.path.exists", return_value=True),
        ):
            result = await sort_document("d1", "Amazon order confirmation total $52.99", "")

        # The prompt sent to the model should contain the similar-doc examples
        call_args = mock_http.post.call_args
        prompt_content = call_args[1]["json"]["messages"][0]["content"]
        assert "Similar documents were previously sorted" in prompt_content
        assert "invoice_2024.pdf" in prompt_content

    @pytest.mark.asyncio
    async def test_sort_works_without_similar_docs(self, temp_dir):
        """When no similar documents exist, sort still works without examples."""
        from app.services.sorting import sort_document

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=_make_query_result([]))
        file_point = MagicMock()
        file_point.id = "pt-1"
        file_point.payload = {"file_path": str(temp_dir / "doc.pdf")}
        mock_qdrant.scroll = AsyncMock(return_value=([file_point], None))
        mock_qdrant.set_payload = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"folder": "medical", "confidence": 0.8})}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"
        mock_settings.sort_confidence_threshold = 0.6

        (temp_dir / "medical").mkdir()

        with (
            patch("app.services.sorting.get_settings", return_value=mock_settings),
            patch("app.services.sorting.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
            patch("app.services.sorting.get_http_client", new_callable=AsyncMock, return_value=mock_http),
            patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.services.sorting.move_file", return_value=str(temp_dir / "medical" / "doc.pdf")),
            patch("os.path.exists", return_value=True),
        ):
            result = await sort_document("d1", "Lab results blood test CBC", "")

        assert result.folder == "medical"
        # Prompt should NOT contain similar-doc section
        call_args = mock_http.post.call_args
        prompt_content = call_args[1]["json"]["messages"][0]["content"]
        assert "Similar documents were previously sorted" not in prompt_content

    @pytest.mark.asyncio
    async def test_review_folder_normalizes(self, temp_dir):
        """The 'review' folder name should normalize to '_review'."""
        from app.services.sorting import sort_document

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=_make_query_result([]))
        file_point = MagicMock()
        file_point.id = "pt-1"
        file_point.payload = {"file_path": str(temp_dir / "doc.pdf")}
        mock_qdrant.scroll = AsyncMock(return_value=([file_point], None))
        mock_qdrant.set_payload = AsyncMock()

        # Model returns "review" (without underscore)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"folder": "review", "confidence": 0.5})}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"
        mock_settings.sort_confidence_threshold = 0.6

        with (
            patch("app.services.sorting.get_settings", return_value=mock_settings),
            patch("app.services.sorting.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
            patch("app.services.sorting.get_http_client", new_callable=AsyncMock, return_value=mock_http),
            patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.services.sorting.move_file", return_value=str(temp_dir / "_review" / "doc.pdf")),
            patch("os.path.exists", return_value=True),
        ):
            result = await sort_document("d1", "Some unclear document", "")

        assert result.folder == "_review"
        assert result.confidence == 0.0  # confidence reset for _review

    @pytest.mark.asyncio
    async def test_low_confidence_goes_to_review(self, temp_dir):
        """Documents with confidence below threshold should go to _review."""
        from app.services.sorting import sort_document

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=_make_query_result([]))
        file_point = MagicMock()
        file_point.id = "pt-1"
        file_point.payload = {"file_path": str(temp_dir / "doc.pdf")}
        mock_qdrant.scroll = AsyncMock(return_value=([file_point], None))
        mock_qdrant.set_payload = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps({"folder": "invoices", "confidence": 0.3})}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)
        mock_settings.qdrant_collection = "documents"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"
        mock_settings.sort_confidence_threshold = 0.6

        (temp_dir / "invoices").mkdir()

        with (
            patch("app.services.sorting.get_settings", return_value=mock_settings),
            patch("app.services.sorting.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
            patch("app.services.sorting.get_http_client", new_callable=AsyncMock, return_value=mock_http),
            patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=[0.1] * 1024),
            patch("app.services.sorting.move_file", return_value=str(temp_dir / "_review" / "doc.pdf")),
            patch("os.path.exists", return_value=True),
        ):
            result = await sort_document("d1", "Ambiguous document", "")

        assert result.folder == "_review"
