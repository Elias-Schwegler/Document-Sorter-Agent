import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.dependencies import ensure_collection, close_clients
from app.services.watcher import start_watcher, stop_watcher
from app.services.backup import start_scheduler, stop_scheduler
from app.services.model_manager import ensure_models_ready
from app.routers import documents, chat, telegram, models, folders, settings, backup, bot
from app.services.telegram_bot import start_bot, stop_bot

logger = logging.getLogger("doc_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Document Manager backend...")
    await ensure_collection()
    logger.info("Qdrant collection ready.")

    asyncio.create_task(ensure_models_ready())
    start_watcher()
    start_scheduler()

    # Start Telegram bot if token is configured
    bot_settings = get_settings()
    if bot_settings.telegram_bot_token:
        try:
            await start_bot()
            logger.info("Telegram bot started (instance: %s).", bot_settings.instance_name)
        except Exception as e:
            logger.error("Failed to start Telegram bot: %s", e)
    else:
        logger.info("Telegram bot not configured (no TELEGRAM_BOT_TOKEN).")

    logger.info("Backend ready.")

    yield

    logger.info("Shutting down...")
    await stop_bot()
    await stop_watcher()
    stop_scheduler()
    await close_clients()


app = FastAPI(
    title="Document Manager API",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(telegram.router, prefix="/api/telegram", tags=["telegram"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(folders.router, prefix="/api/folders", tags=["folders"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(backup.router, prefix="/api/backup", tags=["backup"])
app.include_router(bot.router, prefix="/api/bot", tags=["bot"])


@app.get("/health")
async def health():
    return {"status": "ok"}


# WebSocket for ingestion progress
_ws_clients: set[WebSocket] = set()


@app.websocket("/ws/ingestion")
async def ws_ingestion(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


async def broadcast_ingestion_status(doc_id: str, status: str, detail: str = ""):
    message = json.dumps({"doc_id": doc_id, "status": status, "detail": detail})
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
