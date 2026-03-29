"""Integration tests for /api/folders endpoints."""

import os
from unittest.mock import patch

import pytest

from app.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sorted_folder(temp_dir):
    """Create a temporary 'sorted' directory and patch settings to use it."""
    folder = temp_dir / "sorted"
    folder.mkdir()
    return folder


@pytest.fixture
def _patch_sorted(client, sorted_folder):
    """Patch get_settings so sorted_folder points at our temp directory.

    Depends on ``client`` to ensure the app modules are fully imported
    before we try to patch them.
    """
    fake = Settings(sorted_folder=str(sorted_folder))

    with patch("app.routers.folders.get_settings", return_value=fake):
        yield


# ---------------------------------------------------------------------------
# List folders
# ---------------------------------------------------------------------------


class TestListFolders:

    @pytest.mark.asyncio
    async def test_list_empty(self, client, _patch_sorted):
        response = await client.get("/api/folders")
        assert response.status_code == 200
        assert response.json()["folders"] == []

    @pytest.mark.asyncio
    async def test_list_with_folders(self, client, sorted_folder, _patch_sorted):
        (sorted_folder / "invoices").mkdir()
        (sorted_folder / "receipts").mkdir()
        response = await client.get("/api/folders")
        assert response.status_code == 200
        folders = response.json()["folders"]
        assert "invoices" in folders
        assert "receipts" in folders


# ---------------------------------------------------------------------------
# Create folder
# ---------------------------------------------------------------------------


class TestCreateFolder:

    @pytest.mark.asyncio
    async def test_create_folder(self, client, sorted_folder, _patch_sorted):
        response = await client.post(
            "/api/folders", json={"name": "contracts"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "contracts"
        assert (sorted_folder / "contracts").is_dir()

    @pytest.mark.asyncio
    async def test_create_duplicate(self, client, sorted_folder, _patch_sorted):
        (sorted_folder / "existing").mkdir()
        response = await client.post(
            "/api/folders", json={"name": "existing"}
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_empty_name(self, client, sorted_folder, _patch_sorted):
        # An empty name gets sanitized to "unnamed" by sanitize_filename,
        # so the endpoint creates a folder called "unnamed" rather than
        # rejecting the request.
        response = await client.post("/api/folders", json={"name": ""})
        assert response.status_code == 200
        assert response.json()["name"] == "unnamed"
        assert (sorted_folder / "unnamed").is_dir()


# ---------------------------------------------------------------------------
# Rename folder
# ---------------------------------------------------------------------------


class TestRenameFolder:

    @pytest.mark.asyncio
    async def test_rename_folder(self, client, sorted_folder, _patch_sorted):
        (sorted_folder / "old_name").mkdir()
        response = await client.put(
            "/api/folders/old_name", json={"new_name": "new_name"}
        )
        assert response.status_code == 200
        assert not (sorted_folder / "old_name").exists()
        assert (sorted_folder / "new_name").is_dir()

    @pytest.mark.asyncio
    async def test_rename_nonexistent(self, client, _patch_sorted):
        response = await client.put(
            "/api/folders/ghost", json={"new_name": "anything"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rename_to_existing(self, client, sorted_folder, _patch_sorted):
        (sorted_folder / "src").mkdir()
        (sorted_folder / "dst").mkdir()
        response = await client.put(
            "/api/folders/src", json={"new_name": "dst"}
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Delete folder
# ---------------------------------------------------------------------------


class TestDeleteFolder:

    @pytest.mark.asyncio
    async def test_delete_empty_folder(self, client, sorted_folder, _patch_sorted):
        (sorted_folder / "todelete").mkdir()
        response = await client.delete("/api/folders/todelete")
        assert response.status_code == 200
        assert not (sorted_folder / "todelete").exists()

    @pytest.mark.asyncio
    async def test_delete_nonempty_folder(self, client, sorted_folder, _patch_sorted):
        folder = sorted_folder / "notempty"
        folder.mkdir()
        (folder / "file.txt").write_text("data")
        response = await client.delete("/api/folders/notempty")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, client, _patch_sorted):
        response = await client.delete("/api/folders/nope")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Path traversal prevention
# ---------------------------------------------------------------------------


class TestPathTraversal:

    @pytest.mark.asyncio
    async def test_traversal_rename(self, client, sorted_folder, _patch_sorted):
        """Attempting to rename with path traversal should be rejected."""
        (sorted_folder / "legit").mkdir()
        response = await client.put(
            "/api/folders/legit",
            json={"new_name": "../../etc/passwd"},
        )
        # sanitize_filename will strip the traversal characters,
        # so the result is either a 400 (invalid) or the name gets
        # sanitized and succeeds harmlessly inside the sorted folder.
        # The key assertion: no directory created outside sorted_folder.
        outside = os.path.realpath(
            os.path.join(str(sorted_folder), "../../etc/passwd")
        )
        assert not os.path.exists(outside)

    @pytest.mark.asyncio
    async def test_traversal_create(self, client, sorted_folder, _patch_sorted):
        response = await client.post(
            "/api/folders",
            json={"name": "../../../tmp/evil"},
        )
        outside = os.path.realpath(
            os.path.join(str(sorted_folder), "../../../tmp/evil")
        )
        assert not os.path.exists(outside)
