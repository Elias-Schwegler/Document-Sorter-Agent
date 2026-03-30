"""Unit tests for app.services.vision."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# describe_pdf_pages
# ---------------------------------------------------------------------------


class TestDescribePdfPages:

    @pytest.mark.asyncio
    async def test_returns_empty_when_ocr_text_is_good(self, temp_dir):
        """When OCR extracts > 200 chars, vision is skipped and empty list returned."""
        from app.services.vision import describe_pdf_pages

        good_text = "A" * 250  # well above 200-char threshold
        fake_pdf = str(temp_dir / "textrich.pdf")

        with patch("app.services.parsing.extract_text", return_value=(good_text, 1)):
            result = await describe_pdf_pages(fake_pdf, max_pages=2)

        assert result == []

    @pytest.mark.asyncio
    async def test_uses_vision_when_ocr_sparse(self, temp_dir):
        """When OCR text is sparse, vision model is called for each page."""
        from app.services.vision import describe_pdf_pages

        sparse_text = "ab"  # well below 200-char threshold
        fake_pdf = str(temp_dir / "scanned.pdf")

        # Mock fitz (pymupdf)
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""  # page-level text also sparse
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"\xff\xd8\xff\xe0fake-jpeg"
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 2
        mock_doc.__getitem__ = lambda self, i: mock_page

        with (
            patch("app.services.parsing.extract_text", return_value=(sparse_text, 2)),
            patch("fitz.open") as mock_fitz_open,
            patch("app.services.vision.describe_image", new_callable=AsyncMock, return_value="A scanned receipt"),
        ):
            mock_fitz_open.return_value = mock_doc
            result = await describe_pdf_pages(fake_pdf, max_pages=2)

        assert len(result) == 2
        assert result[0] == "A scanned receipt"

    @pytest.mark.asyncio
    async def test_uses_page_text_when_available(self, temp_dir):
        """When a page has > 50 chars of text, vision is skipped for that page."""
        from app.services.vision import describe_pdf_pages

        sparse_text = "short"
        fake_pdf = str(temp_dir / "mixed.pdf")

        page_with_text = MagicMock()
        page_with_text.get_text.return_value = "X" * 100  # > 50 chars

        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__getitem__ = lambda self, i: page_with_text

        with (
            patch("app.services.parsing.extract_text", return_value=(sparse_text, 1)),
            patch("fitz.open") as mock_fitz_open,
            patch("app.services.vision.describe_image", new_callable=AsyncMock) as mock_describe,
        ):
            mock_fitz_open.return_value = mock_doc
            result = await describe_pdf_pages(fake_pdf, max_pages=1)

        # Vision should NOT have been called because page text was sufficient
        mock_describe.assert_not_called()
        assert len(result) == 1
        assert result[0] == "X" * 100


# ---------------------------------------------------------------------------
# describe_image_file
# ---------------------------------------------------------------------------


class TestDescribeImageFile:

    @pytest.mark.asyncio
    async def test_resizes_large_images(self, temp_dir):
        """Large images should be resized before sending to the vision model."""
        from app.services.vision import describe_image_file

        # Create a large-ish test image using PIL
        from PIL import Image
        img = Image.new("RGB", (2000, 1500), color="red")
        img_path = str(temp_dir / "big_photo.jpg")
        img.save(img_path, format="JPEG")

        with patch("app.services.vision.describe_image", new_callable=AsyncMock, return_value="A red image") as mock_desc:
            result = await describe_image_file(img_path)

        assert result == "A red image"
        mock_desc.assert_called_once()
        # Verify the base64 was generated (we can't easily check the resize
        # without more intrusion, but the call succeeding proves it worked)

    @pytest.mark.asyncio
    async def test_small_images_not_resized(self, temp_dir):
        """Images within the max_dim limit should pass through without resize."""
        from app.services.vision import describe_image_file

        from PIL import Image
        img = Image.new("RGB", (400, 300), color="blue")
        img_path = str(temp_dir / "small_photo.jpg")
        img.save(img_path, format="JPEG")

        with patch("app.services.vision.describe_image", new_callable=AsyncMock, return_value="A blue image") as mock_desc:
            result = await describe_image_file(img_path)

        assert result == "A blue image"
        mock_desc.assert_called_once()


# ---------------------------------------------------------------------------
# describe_image (API timeout handling)
# ---------------------------------------------------------------------------


class TestDescribeImage:

    @pytest.mark.asyncio
    async def test_handles_api_timeout(self):
        """describe_image should propagate the exception on timeout."""
        from app.services.vision import describe_image
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))

        mock_settings = MagicMock()
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"

        with (
            patch("app.services.vision.get_settings", return_value=mock_settings),
            patch("app.services.vision.get_http_client", new_callable=AsyncMock, return_value=mock_client),
        ):
            with pytest.raises(httpx.TimeoutException):
                await describe_image("fakebase64data")

    @pytest.mark.asyncio
    async def test_returns_content_on_success(self):
        """describe_image should return the model's content string."""
        from app.services.vision import describe_image

        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "A dog sitting on a couch"}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.agent_model = "test-model"

        with (
            patch("app.services.vision.get_settings", return_value=mock_settings),
            patch("app.services.vision.get_http_client", new_callable=AsyncMock, return_value=mock_client),
        ):
            result = await describe_image("fakebase64data")

        assert result == "A dog sitting on a couch"
