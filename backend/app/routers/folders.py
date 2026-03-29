import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.utils.file_utils import list_folders, sanitize_filename

logger = logging.getLogger(__name__)

router = APIRouter()


class FolderCreate(BaseModel):
    name: str


class FolderRename(BaseModel):
    new_name: str


# ---------------------------------------------------------------------------
# List folders
# ---------------------------------------------------------------------------


@router.get("/")
async def get_folders():
    """List all folders in the sorted folder."""
    settings = get_settings()
    folders = list_folders(settings.sorted_folder)
    return {"folders": folders}


# ---------------------------------------------------------------------------
# Create folder
# ---------------------------------------------------------------------------


@router.post("/")
async def create_folder(body: FolderCreate):
    """Create a new folder inside the sorted folder."""
    settings = get_settings()
    name = sanitize_filename(body.name.strip())
    if not name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")

    folder_path = os.path.join(settings.sorted_folder, name)
    if os.path.exists(folder_path):
        raise HTTPException(status_code=409, detail="Folder already exists")

    try:
        os.makedirs(folder_path, exist_ok=True)
        logger.info("Created folder: %s", name)
        return {"status": "ok", "name": name, "path": folder_path}
    except OSError as e:
        logger.error("Failed to create folder %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Rename folder
# ---------------------------------------------------------------------------


@router.put("/{name}")
async def rename_folder(name: str, body: FolderRename):
    """Rename a folder inside the sorted folder."""
    settings = get_settings()
    new_name = sanitize_filename(body.new_name.strip())
    if not new_name:
        raise HTTPException(status_code=400, detail="New folder name cannot be empty")

    old_path = os.path.join(settings.sorted_folder, name)
    new_path = os.path.join(settings.sorted_folder, new_name)

    if not os.path.isdir(old_path):
        raise HTTPException(status_code=404, detail="Folder not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="A folder with that name already exists")

    try:
        os.rename(old_path, new_path)
        logger.info("Renamed folder: %s -> %s", name, new_name)
        return {"status": "ok", "old_name": name, "new_name": new_name}
    except OSError as e:
        logger.error("Failed to rename folder %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Delete folder (empty only)
# ---------------------------------------------------------------------------


@router.delete("/{name}")
async def delete_folder(name: str):
    """Delete an empty folder from the sorted folder."""
    settings = get_settings()
    folder_path = os.path.join(settings.sorted_folder, name)

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
        logger.error("Failed to delete folder %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))
