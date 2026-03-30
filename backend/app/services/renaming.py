import json
import os
import re
import logging
from pathlib import Path

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant, get_http_client
from app.models.document import RenameSuggestions
from app.utils.file_utils import sanitize_filename, ensure_unique_path
from app.utils.prompt_templates import RENAME_PROMPT, RENAME_IMAGE_PROMPT

logger = logging.getLogger(__name__)

SCAN_NAME_PATTERN = re.compile(
    r'^(Gescannt|gescannt|scan|Scan|SCAN|IMG|img|image|Image|Document|DOC|doc|photo|Photo|PHOTO|screenshot|Screenshot|Bildschirmfoto|DCIM|DSC|PXL)[\s_\-]',
    re.IGNORECASE
)

def looks_like_scan_name(filename: str) -> bool:
    stem = Path(filename).stem
    return bool(SCAN_NAME_PATTERN.match(stem))


async def suggest_rename(
    doc_id: str, text: str, current_name: str, file_path: str = ""
) -> RenameSuggestions:
    """Use AI to suggest descriptive filenames for a document.

    Calls Ollama chat API with document content and returns a RenameSuggestions
    with up to 3 suggestions. Does NOT apply the rename.

    If text is sparse and file_path points to an image or PDF, uses the vision
    model to describe the image content for better naming.
    """
    settings = get_settings()
    client = await get_http_client()

    # Decide whether to use vision (image analysis) or text-based naming
    use_vision = False
    image_base64 = None
    text_is_sparse = len(text.strip()) < 100

    if file_path and text_is_sparse:
        ext = Path(file_path).suffix.lower().lstrip(".")
        if ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp", "gif", "webp"):
            use_vision = True
            try:
                import base64
                with open(file_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                logger.warning("Failed to read image for vision rename: %s", e)
                use_vision = False
        elif ext == "pdf":
            use_vision = True
            try:
                import base64
                import fitz
                doc = fitz.open(file_path)
                if len(doc) > 0:
                    pix = doc[0].get_pixmap(dpi=150)
                    image_base64 = base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")
                doc.close()
            except Exception as e:
                logger.warning("Failed to render PDF for vision rename: %s", e)
                use_vision = False

    if use_vision and image_base64:
        prompt = RENAME_IMAGE_PROMPT.format(current_name=current_name)
        messages = [{"role": "user", "content": prompt, "images": [image_base64]}]
    else:
        content_preview = text[:2000]
        prompt = RENAME_PROMPT.format(
            current_name=current_name, content=content_preview
        )
        messages = [{"role": "user", "content": prompt}]

    suggestions = []
    try:
        url = settings.ollama_url + "/api/chat"
        response = await client.post(
            url,
            json={
                "model": settings.agent_model,
                "messages": messages,
                "stream": False,
                "think": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        message_content = data.get("message", {}).get("content", "")
        result = json.loads(message_content)

        raw_suggestions = result.get("suggestions", [])
        # Fallback: if old format has suggested_name, wrap in list
        if not raw_suggestions:
            old_name = result.get("suggested_name", "").strip()
            if old_name:
                raw_suggestions = [old_name]

        if not raw_suggestions:
            raw_suggestions = [Path(current_name).stem]

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse rename response: %s", e)
        raw_suggestions = [Path(current_name).stem]
    except Exception as e:
        logger.error("Rename API call failed: %s", e)
        raw_suggestions = [Path(current_name).stem]

    # Sanitize each suggestion and preserve original extension
    ext = Path(current_name).suffix
    for s in raw_suggestions:
        sanitized = sanitize_filename(s.strip())
        if sanitized:
            suggestions.append(sanitized + ext)

    return RenameSuggestions(
        doc_id=doc_id,
        original_name=current_name,
        suggestions=suggestions,
    )


async def store_suggestions(doc_id: str, suggestions: list[str]) -> None:
    settings = get_settings()
    qdrant = await get_qdrant()
    # Find all points for this doc_id and update payload
    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="chunk_index", match=MatchValue(value=0)),
        ]),
        limit=1,
        with_payload=False,
    )
    if points:
        await qdrant.set_payload(
            collection_name=settings.qdrant_collection,
            payload={"rename_suggestions": suggestions},
            points=[points[0].id],
        )


async def apply_rename(doc_id: str, new_name: str) -> str:
    """Rename the document file on disk and update qdrant payload.

    Returns the new file path.
    """
    settings = get_settings()
    qdrant = await get_qdrant()

    # Find current file info from qdrant
    search_results = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
    )

    points, _ = search_results
    if not points:
        raise ValueError(f"Document {doc_id} not found in qdrant")

    current_path = points[0].payload.get("file_path", "")
    if not current_path or not os.path.exists(current_path):
        raise FileNotFoundError(f"File not found: {current_path}")

    # Build new path in same directory
    directory = os.path.dirname(current_path)
    new_name = sanitize_filename(Path(new_name).stem) + Path(new_name).suffix
    new_path = os.path.join(directory, new_name)
    new_path = ensure_unique_path(new_path)

    # Rename on disk
    os.rename(current_path, new_path)

    # Update qdrant payload for all chunks
    all_points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            ]
        ),
        limit=1000,
    )

    for point in all_points:
        payload_update = {
            "filename": os.path.basename(new_path),
            "file_path": new_path,
        }
        await qdrant.set_payload(
            collection_name=settings.qdrant_collection,
            payload=payload_update,
            points=[point.id],
        )

    logger.info("Document %s renamed to %s", doc_id, os.path.basename(new_path))
    return new_path
