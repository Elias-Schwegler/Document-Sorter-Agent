import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.services.model_manager import list_models, pull_model

logger = logging.getLogger(__name__)

router = APIRouter()


class PullRequest(BaseModel):
    model: str


class ActiveModelUpdate(BaseModel):
    agent_model: str | None = None
    embedding_model: str | None = None


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------


@router.get("")
async def get_models():
    """List all available Ollama models."""
    try:
        models = await list_models()
        return {"models": models}
    except Exception as e:
        logger.error("Failed to list models: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list models")


# ---------------------------------------------------------------------------
# Pull model
# ---------------------------------------------------------------------------


@router.post("/pull")
async def pull_model_endpoint(body: PullRequest):
    """Pull a model from Ollama registry, streaming progress."""
    if not body.model.strip():
        raise HTTPException(status_code=400, detail="Model name cannot be empty")

    async def stream_progress():
        async for progress in pull_model(body.model):
            yield f"data: {json.dumps(progress)}\n\n"
        yield f"data: {json.dumps({'status': 'complete'})}\n\n"

    return StreamingResponse(
        stream_progress(),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Active model management (runtime only)
# ---------------------------------------------------------------------------


@router.put("/active")
async def set_active_model(body: ActiveModelUpdate):
    """Update the active agent or embedding model at runtime.

    This does NOT persist to .env -- it only changes the in-memory settings.
    """
    settings = get_settings()

    updated = {}
    if body.agent_model is not None:
        settings.agent_model = body.agent_model
        updated["agent_model"] = body.agent_model
        logger.info("Active agent model changed to: %s", body.agent_model)
    if body.embedding_model is not None:
        settings.embedding_model = body.embedding_model
        updated["embedding_model"] = body.embedding_model
        logger.info("Active embedding model changed to: %s", body.embedding_model)

    if not updated:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of agent_model or embedding_model",
        )

    return {"status": "ok", "updated": updated}


@router.get("/active")
async def get_active_models():
    """Return the currently active agent and embedding models."""
    settings = get_settings()
    return {
        "agent_model": settings.agent_model,
        "embedding_model": settings.embedding_model,
    }
