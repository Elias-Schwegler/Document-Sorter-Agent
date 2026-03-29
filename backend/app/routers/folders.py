import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.utils.file_utils import list_folders, sanitize_filename

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_folder_path(base: str, name: str) -> str:
    """Resolve a folder path and verify it is inside the base directory.

    Raises HTTPException 400 on path-traversal attempts.
    """
    resolved = os.path.realpath(os.path.join(base, name))
    base_resolved = os.path.realpath(base)
    if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return resolved


class FolderCreate(BaseModel):
    name: str


class FolderRename(BaseModel):
    new_name: str


# ---------------------------------------------------------------------------
# List folders
# ---------------------------------------------------------------------------


@router.get("")
async def get_folders():
    """List all folders in the sorted folder."""
    settings = get_settings()
    folders = list_folders(settings.sorted_folder)
    return {"folders": folders}


# ---------------------------------------------------------------------------
# Create folder
# ---------------------------------------------------------------------------


@router.post("")
async def create_folder(body: FolderCreate):
    """Create a new folder inside the sorted folder."""
    settings = get_settings()
    name = sanitize_filename(body.name.strip())
    if not name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")

    folder_path = _safe_folder_path(settings.sorted_folder, name)
    if os.path.exists(folder_path):
        raise HTTPException(status_code=409, detail="Folder already exists")

    try:
        os.makedirs(folder_path, exist_ok=True)
        logger.info("Created folder: %s", name)
        return {"status": "ok", "name": name}
    except OSError as e:
        logger.error("Failed to create folder %s: %s", name, e)
        raise HTTPException(status_code=500, detail="Failed to create folder")


# ---------------------------------------------------------------------------
# Rename folder
# ---------------------------------------------------------------------------


@router.put("/{name}")
async def rename_folder(name: str, body: FolderRename):
    """Rename a folder inside the sorted folder."""
    settings = get_settings()
    old_name = sanitize_filename(name)
    new_name = sanitize_filename(body.new_name.strip())
    if not new_name:
        raise HTTPException(status_code=400, detail="New folder name cannot be empty")

    old_path = _safe_folder_path(settings.sorted_folder, old_name)
    new_path = _safe_folder_path(settings.sorted_folder, new_name)

    if not os.path.isdir(old_path):
        raise HTTPException(status_code=404, detail="Folder not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="A folder with that name already exists")

    try:
        os.rename(old_path, new_path)
        logger.info("Renamed folder: %s -> %s", name, new_name)
        return {"status": "ok", "old_name": name, "new_name": new_name}
    except OSError as e:
        logger.error("Failed to rename folder %s -> %s: %s", old_name, new_name, e)
        raise HTTPException(status_code=500, detail="Failed to rename folder")


# ---------------------------------------------------------------------------
# Delete folder (empty only)
# ---------------------------------------------------------------------------


@router.delete("/{name}")
async def delete_folder(name: str):
    """Delete an empty folder from the sorted folder."""
    settings = get_settings()
    safe_name = sanitize_filename(name)
    folder_path = _safe_folder_path(settings.sorted_folder, safe_name)

    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check if folder is empty
    contents = os.listdir(folder_path)
    if contents:
        raise HTTPException(
            status_code=400,
            detail=f"Folder is not empty ({len(contents)} items). Remove files first.",
        )

    try:
        os.rmdir(folder_path)
        logger.info("Deleted folder: %s", name)
        return {"status": "ok", "name": name}
    except OSError as e:
        logger.error("Failed to delete folder %s: %s", safe_name, e)
        raise HTTPException(status_code=500, detail="Failed to delete folder")
