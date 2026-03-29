import json
import os
import logging
from pathlib import Path

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant, get_http_client
from app.models.document import RenameResult
from app.utils.file_utils import sanitize_filename, ensure_unique_path
from app.utils.prompt_templates import RENAME_PROMPT

logger = logging.getLogger(__name__)


async def suggest_rename(
    doc_id: str, text: str, current_name: str
) -> RenameResult:
    """Use AI to suggest a descriptive filename for a document.

    Calls Ollama chat API with document content and returns a RenameResult
    with the suggested name. Does NOT apply the rename.
    """
    settings = get_settings()
    client = await get_http_client()

    content_preview = text[:2000]
    prompt = RENAME_PROMPT.format(
        current_name=current_name, content=content_preview
    )

    try:
        url = settings.ollama_url + "/api/chat"
        response = await client.post(
            url,
            json={
                "model": settings.agent_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        message_content = data.get("message", {}).get("content", "")
        result = json.loads(message_content)

        suggested = result.get("suggested_name", "").strip()
        if not suggested:
            suggested = Path(current_name).stem

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse rename response: %s", e)
        suggested = Path(current_name).stem
    except Exception as e:
        logger.error("Rename API call failed: %s", e)
        suggested = Path(current_name).stem

    # Sanitize and preserve original extension
    ext = Path(current_name).suffix
    suggested = sanitize_filename(suggested)
    suggested_with_ext = suggested + ext

    return RenameResult(
        doc_id=doc_id,
        original_name=current_name,
        suggested_name=suggested_with_ext,
        applied=False,
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
