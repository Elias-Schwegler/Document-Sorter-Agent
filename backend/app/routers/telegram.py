import json
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant
from pydantic import BaseModel

from app.models.telegram import (
    TelegramAuthStart,
    TelegramAuthVerify,
    TelegramFetchRequest,
    TelegramFetchResponse,
    TelegramMessage,
    TelegramStatus,
)
from app.services.telegram_client import (
    start_auth as tg_start_auth,
    verify_auth as tg_verify_auth,
    is_authenticated as tg_is_authenticated,
    fetch_saved_messages,
    download_message_media,
)
from app.services.ingestion import ingest_document

logger = logging.getLogger(__name__)

router = APIRouter()

class TelegramImportRequest(BaseModel):
    message_ids: list[int]


# In-memory cache of most recently fetched messages
_fetched_messages: list[dict] = []

# Import cancellation flag
_import_cancel = False


@router.post("/auth/start")
async def auth_start(body: TelegramAuthStart):
    """Send an authentication code to the given phone number."""
    try:
        result = await tg_start_auth(phone=body.phone)
        return result
    except Exception as exc:
        logger.error("Auth start failed: %s", exc)
        raise HTTPException(status_code=500, detail="Authentication start failed")


@router.post("/auth/verify")
async def auth_verify(body: TelegramAuthVerify):
    """Verify the authentication code (and optional 2FA password)."""
    try:
        success = await tg_verify_auth(code=body.code, password=body.password)
        if not success:
            raise HTTPException(status_code=401, detail="Authentication failed")
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Auth verify failed: %s", exc)
        raise HTTPException(status_code=500, detail="Authentication verification failed")


@router.get("/status")
async def status():
    """Return the current Telegram authentication status."""
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        return TelegramStatus(authenticated=False, phone=settings.telegram_phone)
    try:
        authed = await tg_is_authenticated()
    except Exception:
        authed = False
    return TelegramStatus(authenticated=authed, phone=settings.telegram_phone)


@router.post("/fetch", response_model=TelegramFetchResponse)
async def fetch_messages(body: TelegramFetchRequest):
    """Fetch saved-messages previews (no download yet)."""
    global _fetched_messages

    if not await tg_is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with Telegram")

    try:
        raw = await fetch_saved_messages(
            limit=body.limit,
            offset_date=body.offset_date,
        )
        _fetched_messages = raw

        messages = [TelegramMessage(**m) for m in raw]
        return TelegramFetchResponse(messages=messages, total=len(messages))
    except Exception as exc:
        logger.error("Fetch failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@router.post("/import")
async def import_messages(body: TelegramImportRequest):
    """Download selected messages and run ingestion on each, streaming progress via SSE."""
    message_ids = body.message_ids
    if not message_ids:
        raise HTTPException(status_code=400, detail="No message_ids provided")

    if not await tg_is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with Telegram")

    async def progress_stream():
        global _import_cancel
        _import_cancel = False

        settings = get_settings()
        dest_folder = settings.watch_folder
        total = len(message_ids)
        completed = 0
        errors = 0

        def _evt(data):
            return f"data: {json.dumps(data)}\n\n"

        def _fname(mid):
            cached = next((m for m in _fetched_messages if m.get("message_id") == mid), {})
            return cached.get("filename") or f"message_{mid}"

        # Build set of already-ingested filenames from Qdrant
        qdrant = await get_qdrant()
        existing_filenames: set[str] = set()
        try:
            scroll_result = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(must=[FieldCondition(key="chunk_index", match=MatchValue(value=0))]),
                limit=10000,
                with_payload=["original_filename"],
            )
            for point in scroll_result[0]:
                name = (point.payload or {}).get("original_filename", "")
                if name:
                    existing_filenames.add(name)
        except Exception as exc:
            logger.warning("Could not check existing docs: %s", exc)

        # Also check files already on disk in watch and sorted folders
        existing_on_disk: set[str] = set()
        for folder in [dest_folder, settings.sorted_folder]:
            for root, _, files in os.walk(folder):
                for f in files:
                    existing_on_disk.add(f)

        # === Phase 1: Download all files first ===
        yield _evt({"type": "phase", "phase": "downloading", "total": total})

        downloaded = []  # list of (idx, mid, filepath, filename)
        already_exists = 0
        for idx, mid in enumerate(message_ids):
            if _import_cancel:
                yield _evt({"type": "stopped", "phase": "downloading", "completed": completed, "downloaded": len(downloaded), "remaining": total - idx})
                return

            fname = _fname(mid)

            # Skip if already ingested or on disk
            if fname and (fname in existing_filenames or fname in existing_on_disk):
                yield _evt({"type": "download", "index": idx, "total": total, "filename": fname, "stage": "exists"})
                already_exists += 1
                continue

            yield _evt({"type": "download", "index": idx, "total": total, "filename": fname, "stage": "downloading"})

            try:
                filepath = await download_message_media(mid, dest_folder)
                if filepath is None:
                    yield _evt({"type": "download", "index": idx, "total": total, "filename": fname, "stage": "skipped"})
                    continue
                actual_fname = os.path.basename(filepath)
                # Double-check the downloaded filename isn't already ingested
                if actual_fname in existing_filenames:
                    yield _evt({"type": "download", "index": idx, "total": total, "filename": actual_fname, "stage": "exists"})
                    os.remove(filepath)
                    already_exists += 1
                    continue
                downloaded.append((idx, mid, filepath, actual_fname))
                existing_on_disk.add(actual_fname)
                yield _evt({"type": "download", "index": idx, "total": total, "filename": actual_fname, "stage": "downloaded"})
            except Exception as exc:
                logger.error("Download failed for message %d: %s", mid, exc)
                yield _evt({"type": "download", "index": idx, "total": total, "filename": fname, "stage": "error", "detail": str(exc)[:100]})

        if already_exists > 0:
            logger.info("Skipped %d already-existing documents", already_exists)

        # === Phase 2: Process (parse, embed, sort) each file ===
        process_total = len(downloaded)
        yield _evt({"type": "phase", "phase": "processing", "total": process_total, "downloaded": total})

        for proc_idx, (orig_idx, mid, filepath, fname) in enumerate(downloaded):
            if _import_cancel:
                yield _evt({"type": "stopped", "phase": "processing", "completed": completed, "processed": proc_idx, "remaining": process_total - proc_idx})
                return

            yield _evt({"type": "process", "index": proc_idx, "total": process_total, "filename": fname, "stage": "parsing"})

            try:
                doc = await ingest_document(filepath, source="telegram")
                yield _evt({"type": "process", "index": proc_idx, "total": process_total, "filename": fname, "stage": "done"})
                completed += 1
            except Exception as exc:
                logger.error("Ingestion failed for %s: %s", fname, exc)
                yield _evt({"type": "process", "index": proc_idx, "total": process_total, "filename": fname, "stage": "error", "detail": str(exc)[:100]})
                errors += 1

        yield _evt({"type": "complete", "total": total, "downloaded": len(downloaded), "completed": completed, "errors": errors})

    return StreamingResponse(progress_stream(), media_type="text/event-stream")


@router.post("/import/stop")
async def stop_import():
    """Stop an in-progress import. Already-downloaded files and processed docs are kept."""
    global _import_cancel
    _import_cancel = True
    return {"status": "ok", "detail": "Import stop requested"}


@router.get("/messages", response_model=TelegramFetchResponse)
async def list_messages():
    """Return the most recently fetched messages from the in-memory cache."""
    messages = [TelegramMessage(**m) for m in _fetched_messages]
    return TelegramFetchResponse(messages=messages, total=len(messages))
