from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Ollama
    ollama_mode: str = "docker"
    ollama_base_url: str = "http://localhost:11434"
    agent_model: str = "qwen3.5:4b"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 1024

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection: str = "documents"

    # Backend
    backend_port: int = 8000
    backend_host: str = "0.0.0.0"
    watch_folder: str = "/app/data/new_documents"
    sorted_folder: str = "/app/data/sorted"
    snapshots_folder: str = "/app/data/qdrant_snapshots"
    telegram_sessions_folder: str = "/app/data/telegram_sessions"

    # Ingestion
    auto_sort: bool = True
    auto_rename: bool = False
    sort_confidence_threshold: float = 0.6

    # Telegram
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_session_name: str = "doc_manager"

    # Backup
    backup_cron: str = "0 2 * * *"
    backup_retention_days: int = 7

    # Chunking
    chunk_size: int = 1500
    chunk_overlap: int = 200

    # OCR
    tesseract_lang: str = "eng"

    # Duplicate detection
    duplicate_threshold: float = 0.95

    # Telegram Bot (BotFather)
    telegram_bot_token: str = ""
    telegram_bot_allowed_users: str = ""
    instance_name: str = "Default"

    @property
    def telegram_bot_allowed_user_ids(self) -> list[int]:
        """Parse comma-separated allowed user IDs into a list of ints."""
        if not self.telegram_bot_allowed_users.strip():
            return []
        ids = []
        for part in self.telegram_bot_allowed_users.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def ollama_url(self) -> str:
        if self.ollama_mode == "external":
            return self.ollama_base_url.rstrip("/")
        return "http://ollama:11434"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
