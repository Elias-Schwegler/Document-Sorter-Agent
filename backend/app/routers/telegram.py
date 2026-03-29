import logging

from fastapi import APIRouter, HTTPException

from app.config import get_settings
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
    """Download selected messages and run ingestion on each."""
    message_ids = body.message_ids
    if not message_ids:
        raise HTTPException(status_code=400, detail="No message_ids provided")

    if not await tg_is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with Telegram")

    settings = get_settings()
    dest_folder = settings.watch_folder

    results: list[dict] = []
    for mid in message_ids:
        try:
            filepath = await download_message_media(mid, dest_folder)
            if filepath is None:
                results.append({"message_id": mid, "status": "skipped", "detail": "no media"})
                continue

            doc = await ingest_document(filepath, source="telegram")
            results.append({
                "message_id": mid,
                "status": "ok",
                "filepath": filepath,
                "document": doc.model_dump() if hasattr(doc, "model_dump") else str(doc),
            })
        except Exception as exc:
            logger.error("Import failed for message %d: %s", mid, exc)
            results.append({"message_id": mid, "status": "error", "detail": "Import failed"})

    return {"imported": len([r for r in results if r["status"] == "ok"]), "results": results}


@router.get("/messages", response_model=TelegramFetchResponse)
async def list_messages():
    """Return the most recently fetched messages from the in-memory cache."""
    messages = [TelegramMessage(**m) for m in _fetched_messages]
    return TelegramFetchResponse(messages=messages, total=len(messages))
