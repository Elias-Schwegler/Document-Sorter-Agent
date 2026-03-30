import base64
import logging

from app.config import get_settings
from app.dependencies import get_http_client

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "Extract the text from this image. Include dates, names, amounts, addresses. "
    "If it's a photo, describe it briefly."
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


async def describe_pdf_pages(filepath: str, max_pages: int = 2) -> list[str]:
    """Render PDF pages as images and describe each with the vision model.

    Only uses vision for pages where OCR produces < 50 chars of text.
    For text-rich pages, uses the OCR text directly (much faster).
    """
    import fitz
    from app.services.parsing import extract_text

    # First try fast OCR extraction
    ocr_text, page_count = extract_text(filepath, lang=get_settings().tesseract_lang)

    # If OCR got good text (> 200 chars), just use it — no vision needed
    if len(ocr_text.strip()) > 200:
        logger.info("PDF has good OCR text (%d chars), skipping vision for %s", len(ocr_text), filepath)
        return []  # Empty = use OCR text from parsing service

    # OCR failed — use vision on first few pages only
    descriptions = []
    doc = fitz.open(filepath)
    num_pages = min(len(doc), max_pages)

    for i in range(num_pages):
        page = doc[i]

        # Try page-level text first
        page_text = page.get_text().strip()
        if len(page_text) > 50:
            descriptions.append(page_text)
            logger.info("Page %d/%d has text (%d chars), skipping vision", i + 1, num_pages, len(page_text))
            continue

        # Page has no/little text — use vision
        pix = page.get_pixmap(dpi=72)  # Low DPI for speed
        img_bytes = pix.tobytes("jpeg")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        logger.info("Describing PDF page %d/%d via vision for %s", i + 1, num_pages, filepath)
        try:
            description = await describe_image(img_b64)
            descriptions.append(description if description else "")
        except Exception:
            descriptions.append("")

    doc.close()
    return descriptions


async def describe_image_file(filepath: str) -> str:
    """Read an image file and describe it with the vision model."""
    from PIL import Image
    import io

    # Resize large images to reduce processing time
    img = Image.open(filepath)
    max_dim = 800
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=75)
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return await describe_image(img_b64)
