import asyncio
import logging
from pathlib import Path

from watchfiles import awatch, Change

from app.config import get_settings
from app.utils.file_utils import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

_watcher_task: asyncio.Task | None = None

# Delay (in seconds) between ingesting files to avoid overloading slow hardware
INGEST_DELAY_SECONDS = 2


async def _is_already_ingested(filename: str) -> bool:
    """Check Qdrant to see if a file with this original_filename already exists."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from app.dependencies import get_qdrant

        settings = get_settings()
        qdrant = await get_qdrant()
        points, _ = await qdrant.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="original_filename",
                        match=MatchValue(value=filename),
                    ),
                    FieldCondition(
                        key="chunk_index",
                        match=MatchValue(value=0),
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(points) > 0
    except Exception:
        logger.exception("Failed to check Qdrant for %s", filename)
        return False


async def _ingest_file(path: Path, source: str = "watcher") -> None:
    """Ingest a single file with error handling."""
    try:
        from app.services.ingestion import ingest_document

        await ingest_document(str(path), source=source)
        logger.info("Ingestion complete for %s", path.name)
    except Exception:
        logger.exception("Failed to ingest %s", path.name)


async def _scan_existing_files(folder: str) -> None:
    """Scan the watch folder for files that exist but haven't been ingested yet."""
    folder_path = Path(folder)
    if not folder_path.exists():
        logger.warning("Watch folder does not exist: %s", folder)
        return

    files = sorted(folder_path.iterdir(), key=lambda p: p.stat().st_mtime)
    pending = []

    for path in files:
        if not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        if await _is_already_ingested(path.name):
            logger.debug("Already ingested, skipping: %s", path.name)
            continue
        pending.append(path)

    if not pending:
        logger.info("Startup scan: no un-ingested files found in %s", folder)
        return

    logger.info(
        "Startup scan: found %d un-ingested file(s) in %s", len(pending), folder
    )

    for path in pending:
        logger.info("Startup ingesting: %s", path.name)
        await _ingest_file(path, source="watcher")
        await asyncio.sleep(INGEST_DELAY_SECONDS)


async def _watch_folder() -> None:
    settings = get_settings()
    folder = settings.watch_folder
    logger.info("File watcher started – monitoring %s", folder)

    # First, process any files that were already in the folder before the watcher started
    try:
        await _scan_existing_files(folder)
    except Exception:
        logger.exception("Startup scan failed")

    try:
        async for changes in awatch(folder):
            for change_type, file_path in changes:
                if change_type != Change.added:
                    continue

                path = Path(file_path)
                ext = path.suffix.lower().lstrip(".")

                if ext not in SUPPORTED_EXTENSIONS:
                    logger.debug(
                        "Ignoring %s – unsupported extension '.%s'", path.name, ext
                    )
                    continue

                logger.info("New file detected: %s", path.name)

                # Small delay to ensure the file is fully written to disk
                await asyncio.sleep(1)

                await _ingest_file(path, source="watcher")

                # Delay between files to avoid overheating on slow hardware
                await asyncio.sleep(INGEST_DELAY_SECONDS)
    except asyncio.CancelledError:
        logger.info("File watcher cancelled")
    except Exception:
        logger.exception("File watcher crashed")


def start_watcher() -> None:
    global _watcher_task

    if _watcher_task is not None and not _watcher_task.done():
        logger.warning("File watcher is already running")
        return

    _watcher_task = asyncio.create_task(_watch_folder())
    logger.info("File watcher task created")


async def stop_watcher() -> None:
    global _watcher_task

    if _watcher_task is None or _watcher_task.done():
        logger.info("File watcher is not running")
        return

    _watcher_task.cancel()
    try:
        await _watcher_task
    except asyncio.CancelledError:
        pass
    _watcher_task = None
    logger.info("File watcher stopped")
