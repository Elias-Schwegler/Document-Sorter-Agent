"""Unit tests for app.services.parsing.extract_text."""

import pytest

from app.services.parsing import extract_text


class TestExtractTextTxt:
    """Plain-text extraction."""

    def test_txt_file(self, sample_txt):
        text, page_count = extract_text(sample_txt)
        assert "sample text document" in text
        assert page_count >= 1

    def test_txt_preserves_content(self, sample_txt):
        text, _ = extract_text(sample_txt)
        assert "multiple lines" in text


class TestExtractTextPdf:
    """PDF extraction (requires pymupdf)."""

    def test_pdf_file(self, sample_pdf):
        text, page_count = extract_text(sample_pdf)
        assert "Hello from the test PDF" in text
        assert page_count == 1

    def test_pdf_multiline(self, sample_pdf):
        text, _ = extract_text(sample_pdf)
        assert "Second line" in text


class TestExtractTextUnsupported:
    """Unsupported or missing files should fail gracefully."""

    def test_unsupported_extension(self, temp_dir):
        path = temp_dir / "data.xyz"
        path.write_text("some data")
        text, pages = extract_text(str(path))
        assert text == ""
        assert pages == 0

    def test_missing_file(self):
        text, pages = extract_text("/nonexistent/path/file.txt")
        assert text == ""
        assert pages == 0

    def test_empty_txt_file(self, temp_dir):
        path = temp_dir / "empty.txt"
        path.write_text("")
        text, pages = extract_text(str(path))
        # An empty file still opens successfully; page_count >= 1
        assert text == ""
        assert pages >= 1
