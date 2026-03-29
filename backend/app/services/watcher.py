import asyncio
import logging
from pathlib import Path

from watchfiles import awatch, Change

from app.config import get_settings
from app.utils.file_utils import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

_watcher_task: asyncio.Task | None = None


async def _watch_folder() -> None:
    settings = get_settings()
    folder = settings.watch_folder
    logger.info("File watcher started – monitoring %s", folder)

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

                try:
                    from app.services.ingestion import ingest_document

                    await ingest_document(str(path), source="watcher")
                    logger.info("Ingestion complete for %s", path.name)
                except Exception:
                    logger.exception("Failed to ingest %s", path.name)
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
