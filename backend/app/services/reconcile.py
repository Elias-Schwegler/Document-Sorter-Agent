import os
import logging
from pathlib import Path
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.config import get_settings
from app.dependencies import get_qdrant

logger = logging.getLogger(__name__)


def _build_filename_index(search_dirs: list[str]) -> dict[str, str]:
    """Build a dict mapping filename -> full_path by walking search directories."""
    index: dict[str, str] = {}
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(search_dir):
            for fname in filenames:
                if fname not in index:
                    index[fname] = os.path.join(dirpath, fname)
    return index


def find_file_on_disk(filename: str, search_dirs: list[str]) -> str | None:
    """Search for a file by name across multiple directories recursively.

    Returns the first match path or None.
    """
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(search_dir):
            if filename in filenames:
                return os.path.join(dirpath, filename)
    return None


def _folder_from_path(file_path: str, sorted_folder: str) -> str:
    """Extract the folder name from a file path relative to sorted_folder.

    E.g. /app/data/sorted/invoices/doc.pdf -> 'invoices'
    Returns empty string if the file is not inside sorted_folder.
    """
    try:
        rel = os.path.relpath(file_path, sorted_folder)
        parts = Path(rel).parts
        if len(parts) >= 2:
            return parts[0]
    except (ValueError, TypeError):
        pass
    return ""


async def reconcile_documents() -> dict:
    """Reconcile Qdrant records with the actual filesystem.

    For each document (chunk_index=0):
      - If file missing: search for it, update or delete from Qdrant
      - If file exists but folder metadata is wrong: update folder
    Returns summary counts.
    """
    settings = get_settings()
    qdrant = await get_qdrant()
    collection = settings.qdrant_collection

    # Build filename -> path lookup once for efficiency
    search_dirs = [settings.sorted_folder, settings.watch_folder]
    file_index = _build_filename_index(search_dirs)

    # Scroll all chunk_index=0 points
    all_docs = []
    offset = None
    while True:
        points, next_offset = await qdrant.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="chunk_index", match=MatchValue(value=0)),
                ]
            ),
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_docs.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    moved = 0
    deleted = 0
    updated = 0
    ok = 0

    for point in all_docs:
        payload = point.payload or {}
        doc_id = payload.get("doc_id", "")
        file_path = payload.get("file_path", "")
        filename = payload.get("filename", "")
        current_folder = payload.get("folder", "")

        try:
            if file_path and os.path.exists(file_path):
                # File exists - check if folder metadata matches actual directory
                actual_folder = _folder_from_path(file_path, settings.sorted_folder)
                if actual_folder and actual_folder != current_folder:
                    # Folder mismatch - update in Qdrant
                    chunk_points, _ = await qdrant.scroll(
                        collection_name=collection,
                        scroll_filter=Filter(must=[
                            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        ]),
                        limit=1000,
                        with_payload=False,
                    )
                    if chunk_points:
                        await qdrant.set_payload(
                            collection_name=collection,
                            payload={"folder": actual_folder},
                            points=[p.id for p in chunk_points],
                        )
                    logger.info("Reconcile folder_updated: %s '%s' -> '%s'",
                                filename, current_folder, actual_folder)
                    updated += 1
                else:
                    ok += 1
            else:
                # File missing from recorded path - try to find it
                found_path = file_index.get(filename)
                if found_path and os.path.exists(found_path):
                    # Found at a new location - update Qdrant
                    new_folder = _folder_from_path(found_path, settings.sorted_folder)
                    chunk_points, _ = await qdrant.scroll(
                        collection_name=collection,
                        scroll_filter=Filter(must=[
                            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        ]),
                        limit=1000,
                        with_payload=False,
                    )
                    if chunk_points:
                        update_payload = {"file_path": found_path}
                        if new_folder:
                            update_payload["folder"] = new_folder
                        await qdrant.set_payload(
                            collection_name=collection,
                            payload=update_payload,
                            points=[p.id for p in chunk_points],
                        )
                    logger.info("Reconcile moved: %s -> %s", filename, found_path)
                    moved += 1
                else:
                    # Truly deleted - remove all chunks from Qdrant
                    chunk_points, _ = await qdrant.scroll(
                        collection_name=collection,
                        scroll_filter=Filter(must=[
                            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        ]),
                        limit=1000,
                        with_payload=False,
                    )
                    if chunk_points:
                        await qdrant.delete(
                            collection_name=collection,
                            points_selector=[p.id for p in chunk_points],
                        )
                    logger.info("Reconcile deleted: %s (doc_id=%s)", filename, doc_id)
                    deleted += 1
        except Exception:
            logger.exception("Reconcile error for doc_id=%s filename=%s", doc_id, filename)

    summary = {"ok": ok, "moved": moved, "deleted": deleted, "updated": updated}
    logger.info("Reconciliation complete: %s", summary)
    return summary
