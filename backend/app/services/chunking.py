import logging

logger = logging.getLogger(__name__)


def chunk_text(
    text: str, chunk_size: int = 1500, overlap: int = 200
) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries.

    Returns a list of chunk strings. If text is shorter than chunk_size,
    returns [text].
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to break at a sentence boundary (". ") within the last
        # portion of the chunk to keep sentences intact.
        search_start = max(start, end - overlap)
        boundary = text.rfind(". ", search_start, end)

        if boundary != -1:
            # Include the period in this chunk
            end = boundary + 1
        else:
            # Try newline as fallback boundary
            boundary = text.rfind("\n", search_start, end)
            if boundary != -1:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start forward, accounting for overlap
        start = end - overlap if end - overlap > start else end

    return chunks
