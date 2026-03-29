import json
import logging
from typing import AsyncGenerator

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import get_settings
from app.dependencies import get_qdrant, get_http_client
from app.models.chat import ChatMessage, SourceReference
from app.services.embedding import embed_text
from app.utils.prompt_templates import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE

logger = logging.getLogger(__name__)

# In-memory conversation history
_conversation_history: list[ChatMessage] = []


async def chat_stream(
    message: str,
    pinned_doc_ids: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """RAG pipeline: embed query, search qdrant, build context, stream response.

    Yields SSE-formatted strings for each token and a final sources message.
    """
    settings = get_settings()
    qdrant = await get_qdrant()
    client = await get_http_client()

    # 1. Embed the user query
    query_embedding = await embed_text(message)
    if not query_embedding:
        yield f"data: {json.dumps({'token': 'Error: failed to embed query.', 'done': False})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
        return

    # 2. Search qdrant for top 5 chunks (score threshold 0.3)
    search_results = await qdrant.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_embedding,
        limit=5,
        score_threshold=0.3,
    )

    # Collect all results keyed by doc_id -> best scoring chunk
    doc_chunks: dict[str, dict] = {}

    for hit in search_results:
        payload = hit.payload or {}
        doc_id = payload.get("doc_id", "")
        if not doc_id:
            continue
        if doc_id not in doc_chunks or hit.score > doc_chunks[doc_id]["score"]:
            doc_chunks[doc_id] = {
                "score": hit.score,
                "payload": payload,
                "point_id": hit.id,
            }

    # 3. If pinned_doc_ids provided, also fetch those docs' chunks
    if pinned_doc_ids:
        for pinned_id in pinned_doc_ids:
            if pinned_id in doc_chunks:
                continue
            pinned_results, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=pinned_id),
                        ),
                        FieldCondition(
                            key="chunk_index",
                            match=MatchValue(value=0),
                        ),
                    ]
                ),
                limit=1,
            )
            if pinned_results:
                point = pinned_results[0]
                payload = point.payload or {}
                doc_chunks[pinned_id] = {
                    "score": 1.0,
                    "payload": payload,
                    "point_id": point.id,
                }

    # 4. Sort by score descending and take top 3
    sorted_docs = sorted(
        doc_chunks.items(), key=lambda x: x[1]["score"], reverse=True
    )[:3]

    # 5. For top 3 docs, get full text
    context_parts: list[str] = []
    sources: list[dict] = []

    for doc_id, info in sorted_docs:
        payload = info["payload"]
        full_text = payload.get("full_text", "")

        # If full_text not on this chunk, fetch chunk_index=0
        if not full_text:
            zero_results, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id),
                        ),
                        FieldCondition(
                            key="chunk_index",
                            match=MatchValue(value=0),
                        ),
                    ]
                ),
                limit=1,
            )
            if zero_results:
                full_text = zero_results[0].payload.get("full_text", "")

        # Fallback: concatenate available chunk_text
        if not full_text:
            all_chunks, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id),
                        ),
                    ]
                ),
                limit=1000,
            )
            all_chunks = sorted(
                all_chunks,
                key=lambda p: p.payload.get("chunk_index", 0),
            )
            full_text = "\n".join(
                p.payload.get("chunk_text", "") for p in all_chunks
            )

        filename = payload.get("filename", "unknown")
        folder = payload.get("folder", "")

        context_parts.append(f"### {filename}\n{full_text[:3000]}")

        sources.append(
            SourceReference(
                doc_id=doc_id,
                filename=filename,
                folder=folder,
                relevance_score=round(info["score"], 4),
                snippet=full_text[:200],
            ).model_dump()
        )

    # 6. Build prompt
    context_str = "\n\n".join(context_parts) if context_parts else "No relevant documents found."
    user_prompt = RAG_CONTEXT_TEMPLATE.format(context=context_str, question=message)

    # Build messages with conversation history
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    for msg in _conversation_history[-10:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_prompt})

    # Store user message in history
    _conversation_history.append(
        ChatMessage(
            role="user",
            content=message,
            pinned_docs=pinned_doc_ids,
        )
    )

    # 7. Call Ollama chat API with stream=true
    url = settings.ollama_url + "/api/chat"
    full_response = ""

    try:
        async with client.stream(
            "POST",
            url,
            json={
                "model": settings.agent_model,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()

            # 8. Yield each token as SSE
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        full_response += token
                        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        logger.error("Ollama chat stream failed: %s", e)
        error_msg = "Error communicating with the language model. Please try again."
        full_response = error_msg
        yield f"data: {json.dumps({'token': error_msg, 'done': False})}\n\n"

    # Store assistant message in history
    _conversation_history.append(
        ChatMessage(
            role="assistant",
            content=full_response,
            sources=[s for s in sources],
        )
    )

    # 9. Yield final sources message
    yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"


def get_history() -> list[ChatMessage]:
    """Return the in-memory conversation history."""
    return list(_conversation_history)


def clear_history() -> None:
    """Clear the in-memory conversation history."""
    _conversation_history.clear()
