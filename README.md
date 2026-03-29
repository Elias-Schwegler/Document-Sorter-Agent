# Document Manager

AI-powered document management system with RAG chat, automatic sorting, intelligent renaming, and Telegram integration. Runs entirely in Docker.

## Features

- **RAG Chat** - Ask questions about your documents using AI with source citations
- **Auto-Sort** - AI classifies documents into folders based on content
- **Smart Rename** - AI suggests descriptive filenames for scanned documents
- **Telegram Import** - Fetch documents from Telegram Saved Messages
- **Document Preview** - View extracted text and PDF previews in-browser
- **Duplicate Detection** - Flags near-duplicate documents before storing
- **Model Selection** - Choose between different Ollama models at runtime
- **Scheduled Backups** - Daily Qdrant snapshots with configurable retention
- **Dark Theme** - Native dark UI

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/Elias-Schwegler/Document-Sorter-Agent.git
cd Document-Sorter-Agent
cp .example_env .env
# Edit .env with your settings
```

### 2. Start with bundled Ollama

```bash
docker compose --profile local-ollama up --build -d
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

```bash
# If using bundled Ollama:
docker compose exec ollama ollama pull qwen3.5:4b
docker compose exec ollama ollama pull qwen3-embedding:4b

# Or use the helper script with external Ollama:
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
                                   :11434
```

| Service | Image | Purpose |
|---------|-------|---------|
| `frontend` | nginx:alpine (~15MB) | React SPA served by nginx |
| `backend` | python:3.12-slim (~250MB) | FastAPI + document processing |
| `qdrant` | qdrant:unprivileged | Vector database |
| `ollama` | ollama/ollama (optional) | LLM inference |

## Configuration

All settings are in `.env`. See `.example_env` for all available options.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODE` | `docker` | `docker` or `external` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | External Ollama URL |
| `AGENT_MODEL` | `qwen3.5:4b` | Model for chat/sorting/renaming |
| `EMBEDDING_MODEL` | `qwen3-embedding:4b` | Model for document embeddings |
| `AUTO_SORT` | `true` | Auto-sort on ingest |
| `AUTO_RENAME` | `false` | Auto-suggest names on ingest |
| `BACKUP_CRON` | `0 2 * * *` | Daily backup schedule |
| `TESSERACT_LANG` | `eng` | OCR language |

## Folder Structure

```
data/
  new_documents/    # Drop files here for auto-ingestion
  sorted/           # AI-organized document folders
  qdrant_storage/   # Qdrant persistent data
  qdrant_snapshots/ # Daily backups
  ollama_models/    # Cached model weights
  telegram_sessions/# Telethon session files
```

## Telegram Setup

1. Get API credentials at [my.telegram.org/apps](https://my.telegram.org/apps)
2. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` in `.env`
3. Use the Telegram page in the UI to authenticate and fetch saved messages

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload documents |
| POST | `/api/chat` | RAG chat (SSE) |
| GET | `/api/models` | List Ollama models |
| POST | `/api/models/pull` | Pull new model |
| POST | `/api/backup/snapshot` | Manual backup |
| GET | `/health` | Health check |

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

## License

MIT
