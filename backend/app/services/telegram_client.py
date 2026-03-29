import os
import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    DocumentAttributeFilename,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    """Return the shared TelegramClient, creating it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        os.makedirs(settings.telegram_sessions_folder, exist_ok=True)
        session_path = os.path.join(
            settings.telegram_sessions_folder,
            settings.telegram_session_name,
        )
        _client = TelegramClient(
            session_path,
            int(settings.telegram_api_id),
            settings.telegram_api_hash,
        )
    return _client


async def start_auth(phone: str = "") -> dict:
    """Send a code request to the given phone number.

    Returns a dict with the phone_code_hash needed for verification.
    """
    settings = get_settings()
    phone = phone or settings.telegram_phone
    client = get_client()

    if not client.is_connected():
        await client.connect()

    result = await client.send_code_request(phone)
    logger.info("Auth code sent to %s", phone)
    return {"phone_code_hash": result.phone_code_hash}


async def verify_auth(
    code: str,
    password: str | None = None,
    phone_code_hash: str | None = None,
) -> bool:
    """Sign in with the received code and optional 2FA password.

    Returns True on success, False otherwise.
    """
    settings = get_settings()
    client = get_client()

    if not client.is_connected():
        await client.connect()

    try:
        await client.sign_in(
            phone=settings.telegram_phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )
    except Exception as exc:
        # SessionPasswordNeeded is raised when 2FA is enabled
        from telethon.errors import SessionPasswordNeededError

        if isinstance(exc, SessionPasswordNeededError):
            if not password:
                raise ValueError("Two-factor authentication password required") from exc
            await client.sign_in(password=password)
        else:
            logger.error("Telegram auth failed: %s", exc)
            return False

    logger.info("Telegram authentication successful")
    return True


async def is_authenticated() -> bool:
    """Check whether the current session is active and authorised."""
    client = get_client()
    try:
        if not client.is_connected():
            await client.connect()
        return await client.is_user_authorized()
    except Exception as exc:
        logger.error("Error checking auth status: %s", exc)
        return False


async def fetch_saved_messages(
    limit: int = 50,
    offset_date: str | None = None,
) -> list[dict]:
    """Fetch messages from Saved Messages that contain media.

    Parameters
    ----------
    limit:
        Maximum number of messages to return.
    offset_date:
        ISO-format datetime string; only messages older than this are returned.

    Returns a list of dicts with message_id, date, media_type, filename,
    file_size, and caption.
    """
    client = get_client()
    if not client.is_connected():
        await client.connect()

    kwargs: dict = {"entity": "me", "limit": limit}
    if offset_date:
        kwargs["offset_date"] = datetime.fromisoformat(offset_date)

    messages: list[dict] = []

    async for msg in client.iter_messages(**kwargs):
        if msg.media is None:
            continue

        media_type: str | None = None
        filename: str | None = None
        file_size: int | None = None

        if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
            doc = msg.media.document
            file_size = doc.size
            mime = getattr(doc, "mime_type", "") or ""

            # Determine media type from mime
            if mime.startswith("video"):
                media_type = "video"
            elif mime.startswith("audio"):
                media_type = "audio"
            else:
                media_type = "document"

            # Extract filename from attributes
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break
        elif isinstance(msg.media, MessageMediaPhoto):
            media_type = "photo"
            # Photos don't expose a direct file_size in the same way
            if msg.media.photo and hasattr(msg.media.photo, "sizes"):
                sizes = msg.media.photo.sizes
                if sizes:
                    last = sizes[-1]
                    file_size = getattr(last, "size", None)
        else:
            # Other media types (geo, contact, etc.) -- skip
            continue

        messages.append(
            {
                "message_id": msg.id,
                "date": msg.date.astimezone(timezone.utc).isoformat(),
                "media_type": media_type,
                "filename": filename,
                "file_size": file_size,
                "caption": msg.message or None,
            }
        )

    logger.info("Fetched %d media messages from Saved Messages", len(messages))
    return messages


async def download_message_media(
    message_id: int,
    dest_folder: str,
) -> str | None:
    """Download media from a specific message to *dest_folder*.

    Returns the local filepath on success, or None if no media was found.
    """
    client = get_client()
    if not client.is_connected():
        await client.connect()

    os.makedirs(dest_folder, exist_ok=True)

    try:
        messages = await client.get_messages("me", ids=message_id)
        msg = messages if not isinstance(messages, list) else (messages[0] if messages else None)

        if msg is None or msg.media is None:
            logger.warning("Message %d has no media to download", message_id)
            return None

        path = await client.download_media(msg, file=dest_folder)
        if path:
            logger.info("Downloaded message %d media to %s", message_id, path)
        return path
    except Exception as exc:
        logger.error("Failed to download media for message %d: %s", message_id, exc)
        return None
