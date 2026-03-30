import os
import logging
import tempfile
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant
from app.models.document import (
    DocumentResponse,
    DocumentListResponse,
    SortResult,
    RenameResult,
    DuplicateInfo,
)
from app.services.ingestion import ingest_document
from app.services.sorting import sort_document
from app.services.renaming import suggest_rename, apply_rename
from app.utils.file_utils import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum file upload size: 100 MB
MAX_UPLOAD_SIZE = 100 * 1024 * 1024


class RenameRequest(BaseModel):
    suggested_name: str = ""
    apply: bool = False


class PendingFile(BaseModel):
    filename: str
    size: int
    modified: str


# ---------------------------------------------------------------------------
# Pending files (downloaded but not yet ingested)
# ---------------------------------------------------------------------------


@router.get("/pending")
async def list_pending_files():
    """List files in the watch folder that haven't been ingested into Qdrant yet."""
    settings = get_settings()
    qdrant = await get_qdrant()
    watch = Path(settings.watch_folder)

    if not watch.exists():
        return {"files": [], "total": 0}

    # Collect all ingested original_filenames from Qdrant
    ingested_names: set[str] = set()
    try:
        points, _ = await qdrant.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="chunk_index",
                        match=MatchValue(value=0),
                    ),
                ]
            ),
            limit=10000,
            with_payload=["original_filename"],
            with_vectors=False,
        )
        for point in points:
            name = (point.payload or {}).get("original_filename", "")
            if name:
                ingested_names.add(name)
    except Exception as exc:
        logger.warning("Could not query Qdrant for pending check: %s", exc)

    pending: list[PendingFile] = []
    for entry in sorted(watch.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_file():
            continue
        ext = entry.suffix.lstrip(".").lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        if entry.name in ingested_names:
            continue
        stat = entry.stat()
        from datetime import datetime, timezone
        pending.append(PendingFile(
            filename=entry.name,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        ))

    return {"files": [f.model_dump() for f in pending], "total": len(pending)}


# ---------------------------------------------------------------------------
# Needs-rename
# ---------------------------------------------------------------------------


@router.get("/needs-rename")
async def get_needs_rename():
    """List documents that need renaming (scan-like names or have stored suggestions)."""
    from app.services.renaming import looks_like_scan_name
    settings = get_settings()
    qdrant = await get_qdrant()
    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(must=[FieldCondition(key="chunk_index", match=MatchValue(value=0))]),
        limit=10000,
        with_payload=True,
    )
    results = []
    for p in points:
        payload = p.payload or {}
        fname = payload.get("filename", "")
        suggestions = payload.get("rename_suggestions", [])
        if looks_like_scan_name(fname) or suggestions:
            results.append({
                "doc_id": payload.get("doc_id", ""),
                "filename": fname,
                "original_filename": payload.get("original_filename", ""),
                "folder": payload.get("folder", ""),
                "file_type": payload.get("file_type", ""),
                "file_size": payload.get("file_size", 0),
                "ingested_at": payload.get("ingested_at", ""),
                "text_preview": (payload.get("full_text", "") or payload.get("chunk_text", ""))[:500],
                "rename_suggestions": suggestions,
            })
    return {"documents": results, "total": len(results)}


# ---------------------------------------------------------------------------
# Bulk rename
# ---------------------------------------------------------------------------


class BulkRenameItem(BaseModel):
    doc_id: str
    new_name: str

class BulkRenameRequest(BaseModel):
    items: list[BulkRenameItem]

@router.post("/bulk-rename")
async def bulk_rename(body: BulkRenameRequest):
    from app.services.renaming import apply_rename
    results = []
    for item in body.items:
        try:
            new_path = await apply_rename(item.doc_id, item.new_name)
            # Clear suggestions
            qdrant = await get_qdrant()
            settings = get_settings()
            points, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=item.doc_id)),
                    FieldCondition(key="chunk_index", match=MatchValue(value=0)),
                ]),
                limit=1, with_payload=False,
            )
            if points:
                await qdrant.set_payload(
                    collection_name=settings.qdrant_collection,
                    payload={"rename_suggestions": []},
                    points=[points[0].id],
                )
            results.append({"doc_id": item.doc_id, "status": "ok", "new_name": os.path.basename(new_path)})
        except Exception as e:
            logger.error("Bulk rename failed for %s: %s", item.doc_id, e)
            results.append({"doc_id": item.doc_id, "status": "error"})
    return {"results": results}


# ---------------------------------------------------------------------------
# Generate suggestions
# ---------------------------------------------------------------------------


@router.post("/{doc_id}/generate-suggestions")
async def generate_suggestions(doc_id: str):
    from app.services.renaming import suggest_rename, store_suggestions
    settings = get_settings()
    qdrant = await get_qdrant()
    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="chunk_index", match=MatchValue(value=0)),
        ]),
        limit=1, with_payload=True,
    )
    if not points:
        raise HTTPException(status_code=404, detail="Document not found")
    payload = points[0].payload or {}
    text = payload.get("full_text", "") or payload.get("chunk_text", "")
    filename = payload.get("filename", "")
    file_path = payload.get("file_path", "")
    result = await suggest_rename(doc_id, text, filename, file_path=file_path)
    if result.suggestions:
        await store_suggestions(doc_id, result.suggestions)
    return {"doc_id": doc_id, "suggestions": result.suggestions}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """Accept one or more files, ingest them, and return results.

    Returns 409 if a duplicate is detected.
    """
    settings = get_settings()
    results: list[dict] = []

    for upload in files:
        ext = Path(upload.filename or "").suffix.lstrip(".").lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({
                "filename": upload.filename,
                "status": "rejected",
                "detail": f"Unsupported file type: .{ext}",
            })
            continue

        # Save to temp file
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, upload.filename or "upload")
        try:
            content = await upload.read()
            if len(content) > MAX_UPLOAD_SIZE:
                results.append({
                    "filename": upload.filename,
                    "status": "rejected",
                    "detail": f"File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024*1024)} MB",
                })
                shutil.rmtree(tmp_dir, ignore_errors=True)
                continue

            with open(tmp_path, "wb") as f:
                f.write(content)

            result = await ingest_document(tmp_path, source="upload")

            if isinstance(result, DuplicateInfo):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Duplicate document detected",
                        "duplicate": result.model_dump(),
                    },
                )

            results.append({
                "filename": result.filename,
                "doc_id": result.doc_id,
                "folder": result.folder,
                "status": "ingested",
            })
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Upload failed for %s: %s", upload.filename, e)
            results.append({
                "filename": upload.filename,
                "status": "error",
                "detail": "Ingestion failed",
            })
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return {"results": results}


# ---------------------------------------------------------------------------
# List all documents
# ---------------------------------------------------------------------------


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """List all documents from qdrant (chunk_index=0 entries only)."""
    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="chunk_index",
                    match=MatchValue(value=0),
                ),
            ]
        ),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    documents = []
    for point in points:
        payload = point.payload or {}
        documents.append(
            DocumentResponse(
                doc_id=payload.get("doc_id", ""),
                filename=payload.get("filename", ""),
                original_filename=payload.get("original_filename", ""),
                folder=payload.get("folder", ""),
                file_type=payload.get("file_type", ""),
                file_size=payload.get("file_size", 0),
                page_count=payload.get("page_count", 0),
                ingested_at=payload.get("ingested_at", ""),
                source=payload.get("source", "upload"),
            )
        )

    return DocumentListResponse(documents=documents, total=len(documents))


# ---------------------------------------------------------------------------
# Get single document
# ---------------------------------------------------------------------------


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str):
    """Get a single document's details including a text preview."""
    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = points[0].payload or {}
    full_text = payload.get("full_text", "")
    text_preview = full_text[:500] if full_text else ""

    return DocumentResponse(
        doc_id=payload.get("doc_id", ""),
        filename=payload.get("filename", ""),
        original_filename=payload.get("original_filename", ""),
        folder=payload.get("folder", ""),
        file_type=payload.get("file_type", ""),
        file_size=payload.get("file_size", 0),
        page_count=payload.get("page_count", 0),
        ingested_at=payload.get("ingested_at", ""),
        source=payload.get("source", "upload"),
        text_preview=text_preview,
    )


# ---------------------------------------------------------------------------
# Download original file
# ---------------------------------------------------------------------------


@router.get("/{doc_id}/download")
async def download_document(doc_id: str):
    """Return the original file for download."""
    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = points[0].payload or {}
    file_path = payload.get("file_path", "")
    filename = payload.get("filename", "download")

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Ensure file_path is within an allowed directory to prevent arbitrary file reads
    resolved = os.path.realpath(file_path)
    allowed_dirs = [
        os.path.realpath(settings.sorted_folder),
        os.path.realpath(settings.watch_folder),
    ]
    if not any(resolved.startswith(d + os.sep) or resolved == d for d in allowed_dirs):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Preview (thumbnail/image of first page)
# ---------------------------------------------------------------------------


@router.get("/{doc_id}/preview")
async def preview_document(doc_id: str):
    """Return a visual preview of the document (first page as image, or the image itself)."""
    from fastapi.responses import Response

    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = points[0].payload or {}
    file_path = payload.get("file_path", "")
    file_type = payload.get("file_type", "")

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    resolved = os.path.realpath(file_path)
    allowed_dirs = [
        os.path.realpath(settings.sorted_folder),
        os.path.realpath(settings.watch_folder),
    ]
    if not any(resolved.startswith(d + os.sep) or resolved == d for d in allowed_dirs):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        if file_type == "image":
            return FileResponse(file_path, media_type="image/jpeg")

        if file_type == "pdf":
            import fitz
            doc = fitz.open(file_path)
            if len(doc) == 0:
                doc.close()
                raise HTTPException(status_code=404, detail="Empty PDF")
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("jpeg")
            doc.close()
            return Response(content=img_bytes, media_type="image/jpeg")

        raise HTTPException(status_code=400, detail="Preview not available for this file type")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Preview generation failed for %s: %s", doc_id, e)
        raise HTTPException(status_code=500, detail="Preview generation failed")


# ---------------------------------------------------------------------------
# Delete document
# ---------------------------------------------------------------------------


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete all chunks from qdrant and the file from disk."""
    settings = get_settings()
    qdrant = await get_qdrant()

    # Find all points for this document
    all_points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            ]
        ),
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )

    if not all_points:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get file path before deleting
    file_path = ""
    for point in all_points:
        fp = (point.payload or {}).get("file_path", "")
        if fp:
            file_path = fp
            break

    # Delete from qdrant
    point_ids = [point.id for point in all_points]
    await qdrant.delete(
        collection_name=settings.qdrant_collection,
        points_selector=point_ids,
    )

    # Delete file from disk
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info("Deleted file: %s", file_path)
        except OSError as e:
            logger.warning("Failed to delete file %s: %s", file_path, e)

    logger.info("Deleted document %s (%d chunks)", doc_id, len(point_ids))
    return {"status": "ok", "doc_id": doc_id, "chunks_deleted": len(point_ids)}


# ---------------------------------------------------------------------------
# Sort document
# ---------------------------------------------------------------------------


@router.post("/{doc_id}/sort", response_model=SortResult)
async def sort_single_document(doc_id: str):
    """Trigger manual sort for a single document."""
    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = points[0].payload or {}
    text = payload.get("full_text", "") or payload.get("chunk_text", "")
    current_folder = payload.get("folder", "")

    result = await sort_document(doc_id, text, current_folder)
    return result


# ---------------------------------------------------------------------------
# Rename document
# ---------------------------------------------------------------------------


@router.post("/{doc_id}/rename", response_model=RenameResult)
async def rename_document(doc_id: str, body: RenameRequest):
    """Suggest or apply a rename for a document.

    If apply=false (or no suggested_name), just suggest a name.
    If apply=true and suggested_name provided, apply the rename.
    """
    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = points[0].payload or {}
    text = payload.get("full_text", "") or payload.get("chunk_text", "")
    current_name = payload.get("filename", "")

    if body.apply and body.suggested_name:
        # Apply the rename
        try:
            new_path = await apply_rename(doc_id, body.suggested_name)
            # Clear rename_suggestions after successful apply
            rename_points, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="chunk_index", match=MatchValue(value=0)),
                ]),
                limit=1, with_payload=False,
            )
            if rename_points:
                await qdrant.set_payload(
                    collection_name=settings.qdrant_collection,
                    payload={"rename_suggestions": []},
                    points=[rename_points[0].id],
                )
            return RenameResult(
                doc_id=doc_id,
                original_name=current_name,
                suggested_name=os.path.basename(new_path),
                applied=True,
            )
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        # Just suggest
        result = await suggest_rename(doc_id, text, current_name)
        return result


# ---------------------------------------------------------------------------
# Bulk sort
# ---------------------------------------------------------------------------


@router.post("/bulk-sort")
async def bulk_sort():
    """Sort all documents in _review or unsorted folders."""
    settings = get_settings()
    qdrant = await get_qdrant()

    # Find all documents in _review or with empty folder
    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="chunk_index",
                    match=MatchValue(value=0),
                ),
            ]
        ),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    # Filter to unsorted documents
    unsorted_docs = []
    for point in points:
        payload = point.payload or {}
        folder = payload.get("folder", "")
        if folder in ("", "_review", "unsorted"):
            unsorted_docs.append(payload)

    results: list[dict] = []
    for doc_payload in unsorted_docs:
        doc_id = doc_payload.get("doc_id", "")
        text = doc_payload.get("full_text", "") or doc_payload.get("chunk_text", "")
        current_folder = doc_payload.get("folder", "")

        try:
            sort_result = await sort_document(doc_id, text, current_folder)
            results.append(sort_result.model_dump())
        except Exception as e:
            logger.error("Bulk sort failed for %s: %s", doc_id, e)
            results.append({
                "doc_id": doc_id,
                "folder": current_folder,
                "confidence": 0.0,
                "error": "Sort failed",
            })

    return {
        "status": "ok",
        "sorted_count": len(results),
        "results": results,
    }
