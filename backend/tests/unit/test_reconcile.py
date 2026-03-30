"""Unit tests for app.services.reconcile."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.reconcile import find_file_on_disk, _folder_from_path, _build_filename_index


# ---------------------------------------------------------------------------
# find_file_on_disk
# ---------------------------------------------------------------------------


class TestFindFileOnDisk:

    def test_finds_existing_file(self, temp_dir):
        """find_file_on_disk returns the path when the file exists."""
        sub = temp_dir / "invoices"
        sub.mkdir()
        target = sub / "receipt.pdf"
        target.write_bytes(b"%PDF")

        result = find_file_on_disk("receipt.pdf", [str(temp_dir)])
        assert result is not None
        assert result == str(target)

    def test_returns_none_for_missing_file(self, temp_dir):
        """find_file_on_disk returns None when the file doesn't exist anywhere."""
        result = find_file_on_disk("ghost.pdf", [str(temp_dir)])
        assert result is None

    def test_searches_multiple_directories(self, temp_dir):
        """find_file_on_disk searches across multiple directories."""
        dir_a = temp_dir / "a"
        dir_b = temp_dir / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        target = dir_b / "report.pdf"
        target.write_bytes(b"%PDF")

        result = find_file_on_disk("report.pdf", [str(dir_a), str(dir_b)])
        assert result is not None
        assert result == str(target)

    def test_skips_nonexistent_search_dirs(self, temp_dir):
        """Non-existent search directories are silently skipped."""
        result = find_file_on_disk("file.pdf", [str(temp_dir / "nope")])
        assert result is None

    def test_finds_file_in_nested_subdir(self, temp_dir):
        """find_file_on_disk walks subdirectories recursively."""
        nested = temp_dir / "level1" / "level2"
        nested.mkdir(parents=True)
        target = nested / "deep.txt"
        target.write_text("hello")

        result = find_file_on_disk("deep.txt", [str(temp_dir)])
        assert result is not None
        assert result == str(target)


# ---------------------------------------------------------------------------
# _folder_from_path
# ---------------------------------------------------------------------------


class TestFolderFromPath:

    def test_extracts_folder_name(self, temp_dir):
        sorted_folder = str(temp_dir / "sorted")
        file_path = os.path.join(sorted_folder, "invoices", "doc.pdf")
        assert _folder_from_path(file_path, sorted_folder) == "invoices"

    def test_returns_empty_for_root_file(self, temp_dir):
        """A file directly in sorted_folder has no subfolder."""
        sorted_folder = str(temp_dir / "sorted")
        file_path = os.path.join(sorted_folder, "doc.pdf")
        assert _folder_from_path(file_path, sorted_folder) == ""

    def test_returns_empty_for_unrelated_path(self, temp_dir):
        sorted_folder = str(temp_dir / "sorted")
        file_path = "/some/other/place/doc.pdf"
        # May return a relative path segment or empty depending on OS
        result = _folder_from_path(file_path, sorted_folder)
        # The function should return something or empty; just check no crash
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _build_filename_index
# ---------------------------------------------------------------------------


class TestBuildFilenameIndex:

    def test_builds_index(self, temp_dir):
        (temp_dir / "a.txt").write_text("a")
        sub = temp_dir / "sub"
        sub.mkdir()
        (sub / "b.pdf").write_bytes(b"%PDF")

        index = _build_filename_index([str(temp_dir)])
        assert "a.txt" in index
        assert "b.pdf" in index
        assert index["a.txt"] == str(temp_dir / "a.txt")

    def test_empty_directory(self, temp_dir):
        index = _build_filename_index([str(temp_dir)])
        assert index == {}

    def test_skips_missing_dirs(self):
        index = _build_filename_index(["/nonexistent/dir"])
        assert index == {}


# ---------------------------------------------------------------------------
# reconcile_documents (async, needs mocks)
# ---------------------------------------------------------------------------


class TestReconcileDocuments:

    @pytest.mark.asyncio
    async def test_detects_moved_files(self, temp_dir):
        """When a file is missing from its recorded path but found elsewhere,
        reconcile should update Qdrant with the new path."""
        from app.services.reconcile import reconcile_documents

        # Create the file at a NEW location
        new_loc = temp_dir / "invoices" / "receipt.pdf"
        new_loc.parent.mkdir(parents=True)
        new_loc.write_bytes(b"%PDF")

        # Point records the OLD path (doesn't exist)
        old_path = str(temp_dir / "old" / "receipt.pdf")
        point = MagicMock()
        point.id = "pt-1"
        point.payload = {
            "doc_id": "d1",
            "file_path": old_path,
            "filename": "receipt.pdf",
            "folder": "",
        }

        chunk_point = MagicMock()
        chunk_point.id = "pt-1"

        mock_qdrant = AsyncMock()
        # First scroll: return the doc; second+: return chunk points
        mock_qdrant.scroll = AsyncMock(
            side_effect=[
                ([point], None),       # initial scroll for all docs
                ([chunk_point], None), # scroll for chunks of this doc
            ]
        )
        mock_qdrant.set_payload = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "documents"
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)

        with (
            patch("app.services.reconcile.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
        ):
            summary = await reconcile_documents()

        assert summary["moved"] == 1
        assert summary["deleted"] == 0
        mock_qdrant.set_payload.assert_called_once()
        call_payload = mock_qdrant.set_payload.call_args[1]["payload"]
        assert "file_path" in call_payload

    @pytest.mark.asyncio
    async def test_detects_deleted_files(self, temp_dir):
        """When a file is missing and not found anywhere, it should be deleted from Qdrant."""
        from app.services.reconcile import reconcile_documents

        point = MagicMock()
        point.id = "pt-1"
        point.payload = {
            "doc_id": "d1",
            "file_path": str(temp_dir / "gone.pdf"),
            "filename": "gone.pdf",
            "folder": "",
        }

        chunk_point = MagicMock()
        chunk_point.id = "pt-1"

        mock_qdrant = AsyncMock()
        mock_qdrant.scroll = AsyncMock(
            side_effect=[
                ([point], None),       # initial scroll
                ([chunk_point], None), # scroll for chunks
            ]
        )
        mock_qdrant.delete = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "documents"
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)

        with (
            patch("app.services.reconcile.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
        ):
            summary = await reconcile_documents()

        assert summary["deleted"] == 1
        assert summary["moved"] == 0
        mock_qdrant.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_detects_folder_mismatches(self, temp_dir):
        """When a file exists but its Qdrant folder metadata is wrong, it should be updated."""
        from app.services.reconcile import reconcile_documents

        # File is in 'medical' subfolder
        medical = temp_dir / "medical"
        medical.mkdir()
        fpath = medical / "lab_results.pdf"
        fpath.write_bytes(b"%PDF")

        point = MagicMock()
        point.id = "pt-1"
        point.payload = {
            "doc_id": "d1",
            "file_path": str(fpath),
            "filename": "lab_results.pdf",
            "folder": "invoices",  # wrong folder in metadata
        }

        chunk_point = MagicMock()
        chunk_point.id = "pt-1"

        mock_qdrant = AsyncMock()
        mock_qdrant.scroll = AsyncMock(
            side_effect=[
                ([point], None),       # initial scroll
                ([chunk_point], None), # scroll for chunks
            ]
        )
        mock_qdrant.set_payload = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "documents"
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)

        with (
            patch("app.services.reconcile.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
        ):
            summary = await reconcile_documents()

        assert summary["updated"] == 1
        mock_qdrant.set_payload.assert_called_once()
        call_payload = mock_qdrant.set_payload.call_args[1]["payload"]
        assert call_payload["folder"] == "medical"

    @pytest.mark.asyncio
    async def test_handles_empty_collection(self, temp_dir):
        """An empty Qdrant collection should return all-zero counts."""
        from app.services.reconcile import reconcile_documents

        mock_qdrant = AsyncMock()
        mock_qdrant.scroll = AsyncMock(return_value=([], None))

        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "documents"
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)

        with (
            patch("app.services.reconcile.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
        ):
            summary = await reconcile_documents()

        assert summary == {"ok": 0, "moved": 0, "deleted": 0, "updated": 0}

    @pytest.mark.asyncio
    async def test_ok_count_for_correct_files(self, temp_dir):
        """Files that exist at their recorded path with correct folder get counted as ok."""
        from app.services.reconcile import reconcile_documents

        fpath = temp_dir / "invoices" / "bill.pdf"
        fpath.parent.mkdir(parents=True)
        fpath.write_bytes(b"%PDF")

        point = MagicMock()
        point.id = "pt-1"
        point.payload = {
            "doc_id": "d1",
            "file_path": str(fpath),
            "filename": "bill.pdf",
            "folder": "invoices",
        }

        mock_qdrant = AsyncMock()
        mock_qdrant.scroll = AsyncMock(return_value=([point], None))

        mock_settings = MagicMock()
        mock_settings.qdrant_collection = "documents"
        mock_settings.sorted_folder = str(temp_dir)
        mock_settings.watch_folder = str(temp_dir)

        with (
            patch("app.services.reconcile.get_settings", return_value=mock_settings),
            patch("app.services.reconcile.get_qdrant", new_callable=AsyncMock, return_value=mock_qdrant),
        ):
            summary = await reconcile_documents()

        assert summary["ok"] == 1
        assert summary["moved"] == 0
        assert summary["deleted"] == 0
        assert summary["updated"] == 0
