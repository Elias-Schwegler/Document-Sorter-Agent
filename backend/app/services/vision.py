import base64
import logging

from app.config import get_settings
from app.dependencies import get_http_client

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "Extract ALL text visible in this document image. "
    "If it's a photo (not a document), describe what you see in detail. "
    "Include any dates, names, amounts, addresses, or other key information."
)


async def describe_image(image_base64: str) -> str:
    """Send an image to the vision model and get a text description/extraction."""
    settings = get_settings()
    client = await get_http_client()
    url = settings.ollama_url + "/api/chat"

    try:
        response = await client.post(
            url,
            json={
                "model": settings.agent_model,
                "messages": [
                    {
                        "role": "user",
                        "content": _VISION_PROMPT,
                        "images": [image_base64],
                    }
                ],
                "stream": False,
                "think": False,
            },
            timeout=600.0,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        logger.info("Vision description: %d chars", len(content))
        return content
    except Exception as e:
        logger.error("Vision describe_image failed: %s (type: %s)", e, type(e).__name__)
        raise


async def describe_pdf_pages(filepath: str, max_pages: int = 5) -> list[str]:
    """Render PDF pages as images and describe each with the vision model."""
    import fitz

    descriptions = []
    doc = fitz.open(filepath)
    num_pages = min(len(doc), max_pages)

    for i in range(num_pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=100)
        img_bytes = pix.tobytes("jpeg")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        logger.info("Describing PDF page %d/%d of %s", i + 1, num_pages, filepath)
        description = await describe_image(img_b64)
        if description:
            descriptions.append(description)
        else:
            descriptions.append("")

    doc.close()
    return descriptions


async def describe_image_file(filepath: str) -> str:
    """Read an image file and describe it with the vision model."""
    with open(filepath, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    return await describe_image(img_b64)
