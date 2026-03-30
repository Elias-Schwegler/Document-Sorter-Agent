import logging

from app.config import get_settings
from app.dependencies import get_http_client

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> list[float]:
    """Embed a single text string via Ollama /api/embed."""
    result = await embed_texts([text])
    return result[0] if result else []


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple text strings via Ollama /api/embed (batch)."""
    if not texts:
        return []
    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/embed"

    try:
        response = await client.post(
            url,
            json={"model": settings.embedding_model, "input": texts},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])
    except Exception as e:
        logger.error("Text embedding failed: %s", e)
        return []


async def embed_query(text: str) -> list[float]:
    """Embed a search query. Same as embed_text for qwen-embedding (no prefix needed)."""
    return await embed_text(text)
