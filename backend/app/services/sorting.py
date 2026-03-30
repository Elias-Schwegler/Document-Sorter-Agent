import json
import os
import logging

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant, get_http_client
from app.models.document import SortResult
from app.utils.file_utils import list_folders, move_file
from app.utils.prompt_templates import SORT_PROMPT

logger = logging.getLogger(__name__)


async def sort_document(
    doc_id: str, text: str, current_folder: str = ""
) -> SortResult:
    """Use AI to determine the appropriate folder for a document.

    Calls Ollama chat API with existing folder names and document content,
    then moves the file to the chosen folder under sorted_folder.
    """
    settings = get_settings()
    client = await get_http_client()
    qdrant = await get_qdrant()

    # Get existing folders
    existing_folders = list_folders(settings.sorted_folder)
    folders_str = ", ".join(existing_folders) if existing_folders else "(none yet)"

    # Find similar documents already sorted (few-shot from user's own data)
    similar_context = ""
    try:
        from app.services.embedding import embed_text
        query_emb = await embed_text(text[:500])
        if query_emb:
            similar = await qdrant.query_points(
                collection_name=settings.qdrant_collection,
                query=query_emb,
                query_filter=Filter(
                    must=[FieldCondition(key="chunk_index", match=MatchValue(value=0))],
                    must_not=[FieldCondition(key="folder", match=MatchValue(value=""))],
                ),
                limit=5,
                score_threshold=0.3,
            )
            examples = []
            seen_folders = set()
            for hit in similar.points:
                p = hit.payload or {}
                f = p.get("folder", "")
                fn = p.get("filename", "")
                if f and f != "_review" and f not in seen_folders:
                    examples.append(f'  - "{fn}" → folder: {f}')
                    seen_folders.add(f)
            if examples:
                similar_context = "\n\nSimilar documents were previously sorted like this:\n" + "\n".join(examples[:5])
    except Exception as e:
        logger.debug("Could not find similar docs for sorting context: %s", e)

    # Build prompt
    content_preview = text[:2000]
    prompt = SORT_PROMPT.format(folders=folders_str, content=content_preview) + similar_context

    # Call Ollama chat API
    url = settings.ollama_url + "/api/chat"
    try:
        response = await client.post(
            url,
            json={
                "model": settings.agent_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        message_content = data.get("message", {}).get("content", "")
        result = json.loads(message_content)

        folder = result.get("folder", "_review").strip().lower()
        confidence = float(result.get("confidence", 0.0))

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse sort response: %s", e)
        folder = "_review"
        confidence = 0.0
    except Exception as e:
        logger.error("Sort API call failed: %s", e)
        folder = "_review"
        confidence = 0.0

    # Normalize: strip underscores from "review" variants
    if folder in ("review", "_review", "unsorted", "_unsorted"):
        folder = "_review"
        confidence = 0.0

    # Apply confidence threshold
    if confidence < settings.sort_confidence_threshold:
        folder = "_review"

    is_new_folder = folder not in existing_folders and folder != "_review"

    # If AI proposes a new folder, store it as pending for user approval
    # Don't auto-create — put in _review with pending_folder metadata
    if is_new_folder:
        logger.info("New folder proposed: '%s' — awaiting approval (doc %s)", folder, doc_id)
        proposed_folder = folder
        folder = "_review"  # Keep in _review until approved
    else:
        proposed_folder = ""

    # Move the file to sorted/{folder}/
    dest_dir = os.path.join(settings.sorted_folder, folder)

    # Find current file path from qdrant
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
    current_path = ""
    if points:
        current_path = points[0].payload.get("file_path", "")

    if current_path and os.path.exists(current_path):
        new_path = move_file(current_path, dest_dir)
        # Update qdrant payload for all chunks of this document
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
            payload_update = {"folder": folder, "file_path": new_path, "pending_folder": proposed_folder}
            await qdrant.set_payload(
                collection_name=settings.qdrant_collection,
                payload=payload_update,
                points=[point.id],
            )
    else:
        logger.warning("File not found for sorting: %s", current_path)

    logger.info("Document %s sorted to folder: %s (confidence=%.2f)", doc_id, folder, confidence)

    return SortResult(
        doc_id=doc_id,
        folder=folder,
        confidence=confidence,
        is_new_folder=is_new_folder,
    )
