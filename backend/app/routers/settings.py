import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services.telegram_bot import is_bot_running

logger = logging.getLogger(__name__)

router = APIRouter()


class SettingsUpdate(BaseModel):
    auto_sort: bool | None = None
    auto_rename: bool | None = None
    agent_model: str | None = None
    embedding_model: str | None = None
    sort_confidence_threshold: float | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    duplicate_threshold: float | None = None
    tesseract_lang: str | None = None


# ---------------------------------------------------------------------------
# Get settings
# ---------------------------------------------------------------------------


@router.get("")
async def get_current_settings():
    """Return a safe subset of current runtime settings."""
    settings = get_settings()
    return {
        "auto_sort": settings.auto_sort,
        "auto_rename": settings.auto_rename,
        "agent_model": settings.agent_model,
        "embedding_model": settings.embedding_model,
        "sort_confidence_threshold": settings.sort_confidence_threshold,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "duplicate_threshold": settings.duplicate_threshold,
        "tesseract_lang": settings.tesseract_lang,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_mode": settings.ollama_mode,
        "watch_folder": settings.watch_folder,
        "sorted_folder": settings.sorted_folder,
        "backup_cron": settings.backup_cron,
        "backup_retention_days": settings.backup_retention_days,
        "telegram_bot_running": is_bot_running(),
        "telegram_bot_configured": bool(settings.telegram_bot_token),
        "instance_name": settings.instance_name,
    }


# ---------------------------------------------------------------------------
# Update settings (runtime only)
# ---------------------------------------------------------------------------


@router.put("")
async def update_settings(body: SettingsUpdate):
    """Update runtime settings. Does NOT persist to .env."""
    settings = get_settings()
    updated = {}

    if body.auto_sort is not None:
        settings.auto_sort = body.auto_sort
        updated["auto_sort"] = body.auto_sort
    if body.auto_rename is not None:
        settings.auto_rename = body.auto_rename
        updated["auto_rename"] = body.auto_rename
    if body.agent_model is not None:
        settings.agent_model = body.agent_model
        updated["agent_model"] = body.agent_model
    if body.embedding_model is not None:
        settings.embedding_model = body.embedding_model
        updated["embedding_model"] = body.embedding_model
    if body.sort_confidence_threshold is not None:
        settings.sort_confidence_threshold = body.sort_confidence_threshold
        updated["sort_confidence_threshold"] = body.sort_confidence_threshold
    if body.chunk_size is not None:
        settings.chunk_size = body.chunk_size
        updated["chunk_size"] = body.chunk_size
    if body.chunk_overlap is not None:
        settings.chunk_overlap = body.chunk_overlap
        updated["chunk_overlap"] = body.chunk_overlap
    if body.duplicate_threshold is not None:
        settings.duplicate_threshold = body.duplicate_threshold
        updated["duplicate_threshold"] = body.duplicate_threshold
    if body.tesseract_lang is not None:
        settings.tesseract_lang = body.tesseract_lang
        updated["tesseract_lang"] = body.tesseract_lang

    if not updated:
        raise HTTPException(status_code=400, detail="No settings provided to update")

    logger.info("Settings updated: %s", updated)
    return {"status": "ok", "updated": updated}
