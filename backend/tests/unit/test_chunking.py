"""Unit tests for app.services.chunking.chunk_text."""

import pytest

from app.services.chunking import chunk_text


class TestChunkTextEmpty:
    """Edge cases that should produce an empty list."""

    def test_empty_string(self):
        assert chunk_text("") == []

    def test_whitespace_only(self):
        assert chunk_text("   \n\t  ") == []

    def test_none_input(self):
        # The implementation guards `if not text`, so None should not crash.
        assert chunk_text(None) == []  # type: ignore[arg-type]


class TestChunkTextSingleChunk:
    """Text shorter than chunk_size should come back as one chunk."""

    def test_short_text(self):
        text = "Hello, world!"
        result = chunk_text(text, chunk_size=1500, overlap=200)
        assert result == [text]

    def test_exactly_chunk_size(self):
        text = "a" * 1500
        result = chunk_text(text, chunk_size=1500, overlap=200)
        assert len(result) == 1
        assert result[0] == text


class TestChunkTextMultipleChunks:
    """Text longer than chunk_size should be split correctly."""

    def test_produces_multiple_chunks(self):
        text = "word " * 1000  # ~5000 chars
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_no_chunk_exceeds_size_by_much(self):
        """Each chunk should be roughly within chunk_size (boundary
        splitting may exceed it by a small amount)."""
        text = "word " * 1000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        for chunk in chunks:
            # Allow some slack for sentence boundary adjustments
            assert len(chunk) <= 600

    def test_all_text_is_covered(self):
        """Reassembling chunks (ignoring overlaps) should reproduce all words."""
        words = [f"w{i}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        combined = " ".join(chunks)
        for word in words:
            assert word in combined


class TestChunkTextOverlap:
    """Verify that consecutive chunks share overlapping content."""

    def test_overlap_exists(self):
        # Build text with sentence boundaries to allow predictable splitting
        sentences = [f"Sentence number {i}." for i in range(50)]
        text = " ".join(sentences)
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) >= 2

        # Check that the end of one chunk overlaps with the start of the next
        for i in range(len(chunks) - 1):
            tail = chunks[i][-40:]  # last 40 chars of current chunk
            head = chunks[i + 1][:80]  # first 80 chars of next chunk
            # At least some words should appear in both
            tail_words = set(tail.split())
            head_words = set(head.split())
            overlap_words = tail_words & head_words
            assert len(overlap_words) > 0, (
                f"No overlap found between chunk {i} and {i+1}"
            )


class TestChunkTextSentenceBoundary:
    """Chunks should prefer to break at sentence boundaries."""

    def test_breaks_at_period(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        # chunk_size just big enough for ~2 sentences
        chunks = chunk_text(text, chunk_size=35, overlap=5)
        # At least one chunk should end with a period (sentence boundary)
        assert any(c.endswith(".") for c in chunks[:-1])

    def test_falls_back_to_newline(self):
        # No periods, but has newlines
        text = "Line one content here\nLine two content here\nLine three content here\nLine four content here"
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        assert len(chunks) >= 2


class TestChunkTextVeryLong:
    """Stress test with very long input."""

    def test_many_chunks(self):
        text = "A" * 100_000
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) >= 90
        # Every chunk should be non-empty
        assert all(c.strip() for c in chunks)
