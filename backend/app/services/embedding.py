import logging

from app.config import get_settings
from app.dependencies import get_http_client

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> list[float]:
    """Embed a single text string using Ollama."""
    results = await embed_texts([text])
    if results:
        return results[0]
    return []


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using Ollama.

    Calls POST /api/embed with the embedding model.
    Returns a list of embedding vectors.
    """
    if not texts:
        return []

    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/embed"

    try:
        response = await client.post(
            url,
            json={
                "model": settings.embedding_model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            logger.warning(
                "Expected %d embeddings, got %d", len(texts), len(embeddings)
            )
        return embeddings
    except Exception as e:
        logger.error("Embedding request failed: %s", e)
        return []
