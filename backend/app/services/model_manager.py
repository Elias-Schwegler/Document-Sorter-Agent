import logging
from typing import AsyncGenerator

from app.config import get_settings
from app.dependencies import get_http_client

logger = logging.getLogger(__name__)


async def ensure_models_ready() -> None:
    """Check that required models exist in Ollama and pull them if missing."""
    settings = get_settings()
    available = await list_models()
    available_names = {m.get("name", "") for m in available}
    # Ollama model names in /api/tags include the tag, e.g. "qwen3.5:4b"
    # Also check without ":latest" suffix
    available_base = set()
    for name in available_names:
        available_base.add(name)
        if ":" in name:
            available_base.add(name.split(":")[0])

    # Only check agent model; embeddings now use local transformers models
    for model in [settings.agent_model]:
        if model not in available_base:
            logger.info("Model %s not found locally, pulling...", model)
            async for progress in pull_model(model):
                status = progress.get("status", "")
                if "pulling" in status or "downloading" in status:
                    completed = progress.get("completed", 0)
                    total = progress.get("total", 0)
                    if total:
                        pct = (completed / total) * 100
                        logger.info("Pulling %s: %.1f%%", model, pct)
            logger.info("Model %s pulled successfully", model)
        else:
            logger.info("Model %s is available", model)


async def list_models() -> list[dict]:
    """List all models available in Ollama.

    Calls GET /api/tags and returns the list of model dicts.
    """
    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/tags"

    try:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])
    except Exception as e:
        logger.error("Failed to list models: %s", e)
        return []


async def pull_model(model_name: str) -> AsyncGenerator[dict, None]:
    """Pull a model from Ollama registry, yielding progress dicts.

    Calls POST /api/pull with stream=true. Each yielded dict contains
    status and optionally completed/total bytes for download progress.
    """
    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/pull"

    import json

    try:
        async with client.stream(
            "POST",
            url,
            json={"model": model_name, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        progress = json.loads(line)
                        yield progress
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("Failed to pull model %s: %s", model_name, e)
        yield {"status": "error", "error": str(e)}


async def get_model_info(model_name: str) -> dict:
    """Get detailed information about a specific model.

    Calls POST /api/show with the model name.
    """
    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/show"

    try:
        response = await client.post(url, json={"model": model_name})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Failed to get model info for %s: %s", model_name, e)
        return {}
