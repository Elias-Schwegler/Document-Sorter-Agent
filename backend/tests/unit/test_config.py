"""Unit tests for app.config.Settings."""

import pytest

from app.config import Settings


class TestSettingsDefaults:
    """Verify sensible default values are set."""

    def test_default_chunk_size(self):
        s = Settings()
        assert s.chunk_size == 1500

    def test_default_chunk_overlap(self):
        s = Settings()
        assert s.chunk_overlap == 200

    def test_default_ollama_mode(self):
        s = Settings()
        assert s.ollama_mode == "docker"

    def test_default_qdrant_collection(self):
        s = Settings()
        assert s.qdrant_collection == "documents"

    def test_default_duplicate_threshold(self):
        s = Settings()
        assert s.duplicate_threshold == 0.95

    def test_default_auto_sort(self):
        s = Settings()
        assert s.auto_sort is True

    def test_default_auto_rename(self):
        s = Settings()
        assert s.auto_rename is False


class TestOllamaUrlProperty:
    """The ollama_url property routes to different URLs based on mode."""

    def test_docker_mode(self):
        s = Settings(ollama_mode="docker")
        assert s.ollama_url == "http://ollama:11434"

    def test_external_mode(self):
        s = Settings(ollama_mode="external", ollama_base_url="http://myhost:11434/")
        assert s.ollama_url == "http://myhost:11434"
        # Trailing slash should be stripped
        assert not s.ollama_url.endswith("/")

    def test_external_mode_no_trailing_slash(self):
        s = Settings(ollama_mode="external", ollama_base_url="http://localhost:11434")
        assert s.ollama_url == "http://localhost:11434"


class TestTelegramBotAllowedUsers:
    """Parsing of the comma-separated allowed user IDs."""

    def test_empty_string(self):
        s = Settings(telegram_bot_allowed_users="")
        assert s.telegram_bot_allowed_user_ids == []

    def test_single_user(self):
        s = Settings(telegram_bot_allowed_users="12345")
        assert s.telegram_bot_allowed_user_ids == [12345]

    def test_multiple_users(self):
        s = Settings(telegram_bot_allowed_users="111, 222, 333")
        assert s.telegram_bot_allowed_user_ids == [111, 222, 333]

    def test_ignores_non_numeric(self):
        s = Settings(telegram_bot_allowed_users="111, abc, 333")
        assert s.telegram_bot_allowed_user_ids == [111, 333]
