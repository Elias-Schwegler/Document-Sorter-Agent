import logging

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer, AutoImageProcessor
from PIL import Image

logger = logging.getLogger(__name__)

_text_model = None
_text_tokenizer = None
_vision_model = None
_vision_processor = None

TEXT_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VISION_MODEL = "nomic-ai/nomic-embed-vision-v1.5"


def _get_text_model():
    global _text_model, _text_tokenizer
    if _text_model is None:
        logger.info("Loading text embedding model: %s", TEXT_MODEL)
        _text_tokenizer = AutoTokenizer.from_pretrained(TEXT_MODEL)
        _text_model = AutoModel.from_pretrained(TEXT_MODEL, trust_remote_code=True)
        _text_model.eval()
        logger.info("Text embedding model loaded")
    return _text_model, _text_tokenizer


def _get_vision_model():
    global _vision_model, _vision_processor
    if _vision_model is None:
        logger.info("Loading vision embedding model: %s", VISION_MODEL)
        _vision_processor = AutoImageProcessor.from_pretrained(VISION_MODEL)
        _vision_model = AutoModel.from_pretrained(VISION_MODEL, trust_remote_code=True)
        _vision_model.eval()
        logger.info("Vision embedding model loaded")
    return _vision_model, _vision_processor


async def embed_text(text: str) -> list[float]:
    """Embed a single text string for document indexing."""
    result = await embed_texts([text])
    return result[0] if result else []


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple text strings. Prefixes with 'search_document: ' for indexing."""
    if not texts:
        return []
    try:
        model, tokenizer = _get_text_model()
        prefixed = [f"search_document: {t}" for t in texts]
        encoded = tokenizer(
            prefixed, padding=True, truncation=True, max_length=8192, return_tensors="pt"
        )
        with torch.no_grad():
            output = model(**encoded)
        embeddings = output.last_hidden_state[:, 0]  # CLS token
        embeddings = F.layer_norm(embeddings, normalized_shape=(embeddings.shape[1],))
        embeddings = F.normalize(embeddings, p=2, dim=1)
        return embeddings.tolist()
    except Exception as e:
        logger.error("Text embedding failed: %s", e)
        return []


async def embed_query(text: str) -> list[float]:
    """Embed a search query. Uses 'search_query: ' prefix."""
    try:
        model, tokenizer = _get_text_model()
        prefixed = [f"search_query: {text}"]
        encoded = tokenizer(
            prefixed, padding=True, truncation=True, max_length=8192, return_tensors="pt"
        )
        with torch.no_grad():
            output = model(**encoded)
        embeddings = output.last_hidden_state[:, 0]
        embeddings = F.layer_norm(embeddings, normalized_shape=(embeddings.shape[1],))
        embeddings = F.normalize(embeddings, p=2, dim=1)
        return embeddings[0].tolist()
    except Exception as e:
        logger.error("Query embedding failed: %s", e)
        return []


async def embed_image(image: Image.Image) -> list[float]:
    """Embed a PIL Image using the vision model."""
    try:
        model, processor = _get_vision_model()
        inputs = processor(image, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs)
        embedding = output.last_hidden_state[:, 0]
        embedding = F.normalize(embedding, p=2, dim=1)
        return embedding[0].tolist()
    except Exception as e:
        logger.error("Image embedding failed: %s", e)
        return []


async def embed_images(images: list[Image.Image]) -> list[list[float]]:
    """Embed multiple PIL Images."""
    results = []
    for img in images:
        emb = await embed_image(img)
        results.append(emb)
    return results
