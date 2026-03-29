import glob
import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.dependencies import get_qdrant

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def create_snapshot() -> dict:
    """Create a Qdrant snapshot, download it, and clean up old snapshots."""
    settings = get_settings()
    collection = settings.qdrant_collection
    snapshots_dir = settings.snapshots_folder
    os.makedirs(snapshots_dir, exist_ok=True)

    try:
        qdrant = await get_qdrant()

        # Create a new snapshot
        logger.info("Creating snapshot for collection '%s'", collection)
        await qdrant.create_snapshot(collection_name=collection)

        # List snapshots and pick the latest one
        snapshots = await qdrant.list_snapshots(collection_name=collection)
        if not snapshots:
            logger.warning("No snapshots found after creation")
            return {"status": "error", "message": "No snapshots found after creation"}

        latest = max(snapshots, key=lambda s: s.creation_time)

        # Download the snapshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{collection}_{timestamp}.snapshot"
        dest_path = os.path.join(snapshots_dir, filename)

        snapshot_file = await qdrant.download_snapshot(
            collection_name=collection,
            snapshot_name=latest.name,
        )

        with open(dest_path, "wb") as f:
            f.write(snapshot_file)

        file_size = os.path.getsize(dest_path)
        logger.info(
            "Snapshot saved: %s (%d bytes)", filename, file_size
        )

        # Clean up old snapshots beyond retention period
        _cleanup_old_snapshots(snapshots_dir, settings.backup_retention_days)

        return {
            "status": "success",
            "filename": filename,
            "size": file_size,
            "path": dest_path,
        }

    except Exception:
        logger.exception("Snapshot creation failed")
        return {"status": "error", "message": "Snapshot creation failed"}


def _cleanup_old_snapshots(snapshots_dir: str, retention_days: int) -> None:
    """Remove snapshot files older than retention_days."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    pattern = os.path.join(snapshots_dir, "*.snapshot")

    for filepath in glob.glob(pattern):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mtime < cutoff:
                os.remove(filepath)
                logger.info("Removed old snapshot: %s", os.path.basename(filepath))
        except OSError:
            logger.exception("Failed to remove snapshot: %s", filepath)


def list_snapshots() -> list[dict]:
    """Return a list of local snapshot files with name, size, and date."""
    settings = get_settings()
    snapshots_dir = settings.snapshots_folder
    pattern = os.path.join(snapshots_dir, "*.snapshot")
    result = []

    for filepath in sorted(glob.glob(pattern), reverse=True):
        try:
            stat = os.stat(filepath)
            result.append({
                "name": os.path.basename(filepath),
                "size": stat.st_size,
                "date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except OSError:
            logger.exception("Failed to stat snapshot: %s", filepath)

    return result


async def trigger_snapshot() -> dict:
    """Manually trigger a snapshot and return the result."""
    logger.info("Manual snapshot triggered")
    return await create_snapshot()


def start_scheduler() -> None:
    """Parse the backup cron expression and start the APScheduler."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Backup scheduler is already running")
        return

    settings = get_settings()
    cron_parts = settings.backup_cron.strip().split()

    if len(cron_parts) != 5:
        logger.error(
            "Invalid BACKUP_CRON expression: '%s' – expected 5 fields",
            settings.backup_cron,
        )
        return

    minute, hour, day, month, day_of_week = cron_parts

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        create_snapshot,
        trigger=CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        ),
        id="qdrant_backup",
        name="Qdrant scheduled backup",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Backup scheduler started with cron: %s", settings.backup_cron)


def stop_scheduler() -> None:
    """Shut down the APScheduler."""
    global _scheduler

    if _scheduler is None or not _scheduler.running:
        logger.info("Backup scheduler is not running")
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Backup scheduler stopped")
