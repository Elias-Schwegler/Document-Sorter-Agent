import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import get_settings

_qdrant_client: AsyncQdrantClient | None = None
_http_client: httpx.AsyncClient | None = None


async def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        _qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=True,
        )
    return _qdrant_client


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _http_client


async def ensure_collection():
    settings = get_settings()
    qdrant = await get_qdrant()
    collections = await qdrant.get_collections()
    existing = [c.name for c in collections.collections]
    if settings.qdrant_collection not in existing:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )


async def close_clients():
    global _qdrant_client, _http_client
    if _qdrant_client:
        await _qdrant_client.close()
        _qdrant_client = None
    if _http_client:
        await _http_client.aclose()
        _http_client = None
