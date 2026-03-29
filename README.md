# Document Manager

AI-powered document management system with RAG chat, automatic sorting, intelligent renaming, and Telegram integration. Runs entirely in Docker.

## Features

- **RAG Chat** - Ask questions about your documents using AI with source citations
- **Auto-Sort** - AI classifies documents into folders based on content
- **Smart Rename** - AI suggests descriptive filenames for scanned documents
- **Telegram Import** - Fetch documents from Telegram Saved Messages (batch download + process)
- **Telegram Bot** - Interact with your documents remotely via @BotFather bot
- **Multi-Instance** - Run on multiple computers, select which one via Telegram `/select`
- **Duplicate Detection** - Flags near-duplicate documents before storing
- **Collision-Proof Import** - Skips already-downloaded/ingested documents on re-import
- **Model Selection** - Choose between different Ollama models at runtime
- **Scheduled Backups** - Daily Qdrant snapshots with configurable retention
- **Import Progress** - Real-time two-phase progress (download, then process)
- **Stop & Resume** - Stop imports gracefully, keeping already-processed documents
- **Multi-Language UI** - English, German, French (selectable in Settings)
- **Dark Theme** - Native dark UI
- **134 Tests** - Unit, integration, and system tests

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/Elias-Schwegler/Document-Sorter-Agent.git
cd Document-Sorter-Agent
cp .example_env .env
# Edit .env with your settings
```

### 2. Start with bundled Ollama (CPU)

```bash
docker compose --profile local-ollama up --build -d
```

### 2b. Start with bundled Ollama (NVIDIA GPU)

```bash
docker compose --profile local-ollama-gpu up --build -d
```

### 3. Start with external Ollama

If you already have Ollama running locally:

```bash
# In .env, set:
# OLLAMA_MODE=external
# OLLAMA_BASE_URL=http://host.docker.internal:11434

docker compose up --build -d
```

### 4. Pull models (first run)

Models are auto-pulled on startup, or manually:

```bash
# Via Ollama API (recommended):
curl http://localhost:11434/api/pull -d '{"name":"qwen3.5:0.8b"}'
curl http://localhost:11434/api/pull -d '{"name":"qwen3-embedding:0.6b"}'

# Or use the helper script:
bash scripts/pull_models.sh http://localhost:11434
```

### 5. Open the UI

Navigate to [http://localhost:3000](http://localhost:3000)

## Architecture

```
Frontend (React)  -->  Backend (FastAPI)  -->  Qdrant (Vector DB)
    :3000                 :8000                   :6333
                            |
                            +--> Ollama (LLM)
                            |      :11434
                            |
                            +--> Telegram Bot API
```

| Service | Image | Purpose |
|---------|-------|---------|
| `frontend` | nginx:alpine (~15MB) | React SPA served by nginx |
| `backend` | python:3.12-slim (~250MB) | FastAPI + document processing + Telegram bot |
| `qdrant` | qdrant/qdrant:v1.16.2-unprivileged | Vector database |
| `ollama` | ollama/ollama (optional) | LLM inference (CPU or GPU) |

## Configuration

All settings are in `.env`. See `.example_env` for all available options.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODE` | `docker` | `docker` or `external` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | External Ollama URL |
| `AGENT_MODEL` | `qwen3.5:4b` | Model for chat/sorting/renaming |
| `EMBEDDING_MODEL` | `qwen3-embedding:4b` | Model for document embeddings |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector dimensions (must match model) |
| `AUTO_SORT` | `true` | Auto-sort on ingest |
| `AUTO_RENAME` | `false` | Auto-suggest names on ingest |
| `BACKUP_CRON` | `0 2 * * *` | Daily backup schedule |
| `TESSERACT_LANG` | `eng` | OCR language (e.g., `eng+deu`) |
| `TELEGRAM_BOT_TOKEN` | | BotFather bot token |
| `INSTANCE_NAME` | `Default` | Instance name for multi-computer support |
| `TELEGRAM_BOT_ALLOWED_USERS` | | Comma-separated Telegram user IDs |

### Recommended models by hardware

| Hardware | Agent Model | Embedding Model | RAM Usage |
|----------|-------------|-----------------|-----------|
| 16GB RAM, CPU only | `qwen3.5:0.8b` | `qwen3-embedding:0.6b` | ~3GB |
| 32GB RAM, CPU | `qwen3.5:4b` | `qwen3-embedding:0.6b` | ~5GB |
| GPU (8GB+ VRAM) | `qwen3.5:4b` | `qwen3-embedding:4b` | ~7GB |

## Folder Structure

```
data/
  new_documents/    # Drop files here for auto-ingestion
  sorted/           # AI-organized document folders
  qdrant_storage/   # Qdrant persistent data
  qdrant_snapshots/ # Daily backups
  ollama_models/    # Cached model weights (Docker volume)
  telegram_sessions/# Telethon session files
```

## Telegram Setup

### Saved Messages Import (Telethon)

1. Get API credentials at [my.telegram.org/apps](https://my.telegram.org/apps)
2. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` in `.env`
3. Restart the backend
4. Use the Telegram page in the UI to authenticate and fetch saved messages

### Bot (BotFather)

1. Message [@BotFather](https://t.me/BotFather) on Telegram, create a bot with `/newbot`
2. Copy the token and set `TELEGRAM_BOT_TOKEN` in `.env`
3. Set `INSTANCE_NAME` (e.g., `Home PC`, `Work Laptop`) for multi-computer support
4. Optionally set `TELEGRAM_BOT_ALLOWED_USERS` to restrict access
5. Restart the backend - the bot starts automatically

**Bot commands:**
- `/search <query>` - Search documents via RAG
- `/ask <question>` - Ask about your documents
- `/list` - Browse documents
- `/send <filename>` - Get a document sent to you
- `/rename <doc_id>` - AI rename suggestion
- `/select` - Choose which computer instance to talk to
- Just type a message for implicit `/ask`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload documents |
| GET | `/api/documents` | List all documents |
| POST | `/api/chat` | RAG chat (SSE streaming) |
| GET | `/api/models` | List Ollama models |
| POST | `/api/models/pull` | Pull new model (SSE progress) |
| GET | `/api/folders` | List folders |
| POST | `/api/telegram/import` | Import from Telegram (SSE progress) |
| POST | `/api/telegram/import/stop` | Stop in-progress import |
| GET | `/api/bot/status` | Bot status |
| POST | `/api/backup/snapshot` | Manual backup |
| GET | `/health` | Health check |

## Testing

```bash
cd backend
pip install -r requirements-test.txt
pytest tests/ -v
```

134 tests covering unit, integration, and system tests.

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Security

- Path traversal protection on all file operations
- Upload size limit (100MB)
- Input validation via Pydantic models
- CORS configured (no credentials)
- Error messages sanitized (no internal paths leaked)
- Telegram bot restricted to allowed user IDs

## License

MIT
