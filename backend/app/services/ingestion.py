import os
import uuid
import logging
from datetime import datetime, timezone

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant
from app.models.document import DocumentMetadata, DuplicateInfo
from PIL import Image as PILImage

from app.services.parsing import extract_text
from app.services.chunking import chunk_text
from app.services.embedding import embed_text, embed_texts, embed_image, embed_images
from app.services.renaming import looks_like_scan_name
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

    embeddings = []
    if file_type == "pdf":
        # Render PDF pages as images and embed each with vision model.
        # Replace text chunks with per-page text so len(chunks) == len(embeddings).
        try:
            import fitz as fitz_lib

            doc_pdf = fitz_lib.open(filepath)
            page_texts = []
            page_images = []
            for page in doc_pdf:
                page_text = page.get_text().strip()
                if not page_text:
                    # OCR fallback for scanned pages
                    from app.services.parsing import _ocr_page_image

                    page_text = _ocr_page_image(page, settings.tesseract_lang)
                page_texts.append(page_text if page_text else "")
                pix = page.get_pixmap(dpi=150)
                img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_images.append(img)
            doc_pdf.close()

            embeddings = await embed_images(page_images)
            # Use per-page text as chunks (one chunk per page)
            if page_texts:
                chunks = page_texts
        except Exception as e:
            logger.warning("Vision embedding failed for PDF: %s, falling back to text", e)
            embeddings = await embed_texts(chunks)
    elif file_type == "image":
        # Embed the image directly with vision model
        try:
            img = PILImage.open(filepath).convert("RGB")
            emb = await embed_image(img)
            if emb:
                embeddings = [emb]
        except Exception as e:
            logger.warning("Vision embedding failed for image: %s", e)
        if not embeddings:
            embeddings = await embed_texts(chunks)
    else:
        # Text-based files: embed text chunks
        embeddings = await embed_texts(chunks)

    if not embeddings:
        logger.error("Failed to generate embeddings for %s", filepath)
        raise RuntimeError(f"Embedding failed for {filepath}")

    # Ensure chunks and embeddings are aligned
    if len(embeddings) != len(chunks):
        # Truncate to the shorter list to keep them paired
        min_len = min(len(embeddings), len(chunks))
        embeddings = embeddings[:min_len]
        chunks = chunks[:min_len]

    # --- Duplicate check ---
    if embeddings:
        first_embedding = embeddings[0]
        query_response = await qdrant.query_points(
            collection_name=settings.qdrant_collection,
            query=first_embedding,
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

        if query_response.points:
            match = query_response.points[0]
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
            "rename_suggestions": [],
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

            rename_result = await suggest_rename(doc_id, text, filename, file_path=filepath)
            if rename_result.suggestions:
                new_path = await apply_rename(doc_id, rename_result.suggestions[0])
                doc_meta.filename = os.path.basename(new_path)
                doc_meta.file_path = new_path
        except Exception as e:
            logger.error("Auto-rename failed for %s: %s", doc_id, e)
    elif looks_like_scan_name(filename):
        # Generate suggestions but don't apply - user reviews on rename page
        try:
            from app.services.renaming import suggest_rename, store_suggestions

            rename_result = await suggest_rename(doc_id, text, filename, file_path=filepath)
            if rename_result.suggestions:
                await store_suggestions(doc_id, rename_result.suggestions)
                logger.info("Stored %d rename suggestions for %s", len(rename_result.suggestions), filename)
        except Exception as e:
            logger.error("Failed to generate rename suggestions for %s: %s", doc_id, e)

    if ws_callback:
        await ws_callback("complete")

    logger.info("Document ingested: %s (doc_id=%s, chunks=%d)", filename, doc_id, len(chunks))
    return doc_meta
