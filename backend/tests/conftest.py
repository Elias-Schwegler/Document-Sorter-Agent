"""Shared fixtures for the Document Manager test suite.

Provides an async httpx test client, temp directories, sample files,
and mocks for external services (Qdrant, Ollama) so tests can run
without Docker.
"""

import importlib
import os
import sys
import tempfile
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx


# ---------------------------------------------------------------------------
# Stub out third-party packages that may not be installed locally.
# These are only needed at import time by app modules; their real
# behaviour is always mocked in tests.
# ---------------------------------------------------------------------------

def _ensure_stub(name: str):
    """Insert a stub module with MagicMock attributes if not installed."""
    if name in sys.modules:
        return
    try:
        importlib.import_module(name)
    except (ImportError, ModuleNotFoundError):
        mod = types.ModuleType(name)
        # Make attribute access return MagicMock so `from X import Y` works
        mod.__dict__["__getattr__"] = lambda attr: MagicMock()
        sys.modules[name] = mod

_OPTIONAL_DEPS = [
    # Filesystem watcher
    "watchfiles",
    # Scheduler
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.asyncio",
    "apscheduler.triggers",
    "apscheduler.triggers.cron",
    # OCR
    "pytesseract",
    # Document formats
    "docx",
    "openpyxl",
    # Telegram (python-telegram-bot)
    "telegram",
    "telegram.ext",
    "telegram.constants",
    # Telethon
    "telethon",
    "telethon.sessions",
    "telethon.tl",
    "telethon.tl.types",
]

for _dep in _OPTIONAL_DEPS:
    _ensure_stub(_dep)


# ---------------------------------------------------------------------------
# Now pre-import all app.services.* and app.routers.* submodules so that
# unittest.mock.patch() can resolve dotted paths like
# "app.services.telegram_bot.start_bot".
# ---------------------------------------------------------------------------
import app.dependencies  # noqa: E402
import app.services.watcher  # noqa: E402
import app.services.backup  # noqa: E402
import app.services.model_manager  # noqa: E402
import app.services.telegram_bot  # noqa: E402
import app.services.embedding  # noqa: E402
import app.routers.documents  # noqa: E402
import app.routers.folders  # noqa: E402
import app.routers.settings  # noqa: E402
import app.routers.chat  # noqa: E402


# ---------------------------------------------------------------------------
# Temporary directory & sample files  (needed by ALL test tiers)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir(tmp_path):
    """Return a temporary directory path (pathlib.Path)."""
    return tmp_path


@pytest.fixture
def sample_txt(temp_dir):
    """Create a small .txt file and return its path as a string."""
    path = temp_dir / "sample.txt"
    path.write_text(
        "This is a sample text document.\n"
        "It has multiple lines for testing purposes.\n"
        "Line three of the document.\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def sample_pdf(temp_dir):
    """Create a minimal single-page PDF using pymupdf and return its path."""
    import fitz  # pymupdf

    path = str(temp_dir / "sample.pdf")
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello from the test PDF.\nSecond line of text.")
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# Mock Qdrant client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_qdrant():
    """Return an AsyncMock that behaves like AsyncQdrantClient."""
    qdrant = AsyncMock()
    qdrant.scroll = AsyncMock(return_value=([], None))
    qdrant.search = AsyncMock(return_value=[])
    qdrant.upsert = AsyncMock()
    qdrant.delete = AsyncMock()
    qdrant.get_collections = AsyncMock(
        return_value=MagicMock(collections=[])
    )
    return qdrant


# ---------------------------------------------------------------------------
# Mock Ollama embedding response
# ---------------------------------------------------------------------------

def make_embedding(dim: int = 1024) -> list[float]:
    """Return a deterministic fake embedding vector."""
    return [0.01 * (i % 100) for i in range(dim)]


@pytest.fixture
def mock_embed():
    """Patch embed_texts to return fake embeddings without calling Ollama."""
    async def _fake_embed_texts(texts):
        return [make_embedding() for _ in texts]

    async def _fake_embed_text(text):
        return make_embedding()

    with (
        patch("app.services.embedding.embed_texts", side_effect=_fake_embed_texts),
        patch("app.services.embedding.embed_text", side_effect=_fake_embed_text),
    ):
        yield


# ---------------------------------------------------------------------------
# FastAPI async test client (integration / system tests only)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    """Yield an httpx.AsyncClient bound to the test app.

    All heavy lifespan side-effects (Qdrant init, watcher, scheduler,
    Telegram bot) are patched out so the app starts cleanly.
    """
    with (
        patch("app.dependencies.ensure_collection", new_callable=AsyncMock),
        patch("app.dependencies.close_clients", new_callable=AsyncMock),
        patch("app.services.watcher.start_watcher", lambda: None),
        patch("app.services.watcher.stop_watcher", new_callable=AsyncMock),
        patch("app.services.backup.start_scheduler", lambda: None),
        patch("app.services.backup.stop_scheduler", lambda: None),
        patch("app.services.model_manager.ensure_models_ready", new_callable=AsyncMock),
        patch("app.services.telegram_bot.start_bot", new_callable=AsyncMock),
        patch("app.services.telegram_bot.stop_bot", new_callable=AsyncMock),
        patch("app.services.telegram_bot.is_bot_running", return_value=False),
    ):
        from app.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
