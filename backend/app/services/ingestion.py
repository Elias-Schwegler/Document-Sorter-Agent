import os
import uuid
import logging
from datetime import datetime, timezone

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant
from app.models.document import DocumentMetadata, DuplicateInfo
from app.services.parsing import extract_text
from app.services.chunking import chunk_text
from app.services.embedding import embed_text, embed_texts
from app.utils.file_utils import get_file_type, get_file_size

logger = logging.getLogger(__name__)


async def ingest_document(
    filepath: str,
    source: str = "upload",
    ws_callback=None,
) -> DocumentMetadata | DuplicateInfo:
    """Orchestrate full document ingestion pipeline.

    Steps: parse -> chunk -> embed -> duplicate check -> store in qdrant
           -> optionally sort/rename.

    If ws_callback is provided, it is called with status strings.
    Returns DocumentMetadata on success, or DuplicateInfo if a duplicate is detected.
    """
    settings = get_settings()
    qdrant = await get_qdrant()

    doc_id = str(uuid.uuid4())
    filename = os.path.basename(filepath)
    file_type = get_file_type(filename)
    file_size = get_file_size(filepath)

    # --- Parsing ---
    if ws_callback:
        await ws_callback("parsing")

    text, page_count = extract_text(filepath, lang=settings.tesseract_lang)
    if not text.strip():
        logger.warning("No text extracted from %s", filepath)
        text = ""

    # --- Chunking ---
    if ws_callback:
        await ws_callback("chunking")

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        chunks = [text] if text else [""]

    # --- Embedding ---
    if ws_callback:
        await ws_callback("embedding")

    embeddings = await embed_texts(chunks)
    if not embeddings:
        logger.error("Failed to generate embeddings for %s", filepath)
        raise RuntimeError(f"Embedding failed for {filepath}")

    # --- Duplicate check ---
    if embeddings:
        first_embedding = embeddings[0]
        search_results = await qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=first_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="chunk_index",
                        match=MatchValue(value=0),
                    )
                ]
            ),
            limit=1,
            score_threshold=settings.duplicate_threshold,
        )

        if search_results:
            match = search_results[0]
            payload = match.payload or {}
            logger.info(
                "Duplicate detected for %s (score=%.4f, existing=%s)",
                filename,
                match.score,
                payload.get("filename", "unknown"),
            )
            return DuplicateInfo(
                doc_id=doc_id,
                existing_doc_id=payload.get("doc_id", ""),
                existing_filename=payload.get("filename", "unknown"),
                similarity=match.score,
            )

    # --- Store in Qdrant ---
    if ws_callback:
        await ws_callback("storing")

    ingested_at = datetime.now(timezone.utc).isoformat()

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "doc_id": doc_id,
            "chunk_index": i,
            "chunk_text": chunk,
            "filename": filename,
            "original_filename": filename,
            "folder": "",
            "file_path": filepath,
            "file_type": file_type,
            "file_size": file_size,
            "page_count": page_count,
            "ingested_at": ingested_at,
            "source": source,
        }
        # Store full text only on the first chunk
        if i == 0:
            payload["full_text"] = text

        points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

    await qdrant.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
    )

    doc_meta = DocumentMetadata(
        doc_id=doc_id,
        filename=filename,
        original_filename=filename,
        folder="",
        file_path=filepath,
        file_type=file_type,
        file_size=file_size,
        page_count=page_count,
        ingested_at=ingested_at,
        source=source,
    )

    # --- Sorting ---
    if settings.auto_sort:
        if ws_callback:
            await ws_callback("sorting")
        try:
            from app.services.sorting import sort_document

            sort_result = await sort_document(doc_id, text, "")
            doc_meta.folder = sort_result.folder
            # Update file_path after sort moves the file
            updated_path = os.path.join(
                settings.sorted_folder, sort_result.folder, filename
            )
            if os.path.exists(updated_path):
                doc_meta.file_path = updated_path
        except Exception as e:
            logger.error("Auto-sort failed for %s: %s", doc_id, e)

    # --- Renaming ---
    if settings.auto_rename:
        try:
            from app.services.renaming import suggest_rename, apply_rename

            rename_result = await suggest_rename(doc_id, text, filename)
            if rename_result.suggested_name:
                new_path = await apply_rename(doc_id, rename_result.suggested_name)
                doc_meta.filename = os.path.basename(new_path)
                doc_meta.file_path = new_path
        except Exception as e:
            logger.error("Auto-rename failed for %s: %s", doc_id, e)

    if ws_callback:
        await ws_callback("complete")

    logger.info("Document ingested: %s (doc_id=%s, chunks=%d)", filename, doc_id, len(chunks))
    return doc_meta
