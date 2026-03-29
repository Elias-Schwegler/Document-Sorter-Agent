import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatHistoryResponse
from app.services.rag import chat_stream, get_history, clear_history

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/")
async def chat(request: ChatRequest):
    """Stream a RAG-powered chat response as Server-Sent Events."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        return StreamingResponse(
            chat_stream(request.message, request.pinned_doc_ids),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.error("Chat endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=ChatHistoryResponse)
async def history():
    """Return the in-memory chat history."""
    messages = get_history()
    return ChatHistoryResponse(messages=messages)


@router.delete("/history")
async def delete_history():
    """Clear the in-memory chat history."""
    clear_history()
    return {"status": "ok", "message": "Chat history cleared"}
