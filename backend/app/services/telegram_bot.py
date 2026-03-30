"""Telegram BotFather bot integration for Document Manager.

Allows users to interact with the document manager via a Telegram bot:
- Search / ask questions about documents (RAG)
- List documents
- Send documents back to the user
- Rename documents with AI suggestions
- Multi-instance support (select which computer to talk to)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import get_settings

logger = logging.getLogger("doc_manager.telegram_bot")

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_application: Application | None = None
_bot_running: bool = False

# Per-user selected instance: {telegram_user_id: instance_name}
_user_selected_instance: dict[int, str] = {}

# Instance registry: {instance_name: {base_url, last_seen}}
_instance_registry: dict[str, dict] = {}

# Pagination state: {telegram_user_id: offset}
_user_list_offset: dict[int, int] = {}

PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_user_allowed(user_id: int) -> bool:
    """Check if a Telegram user is allowed to use the bot."""
    settings = get_settings()
    allowed = settings.telegram_bot_allowed_user_ids
    if not allowed:
        return True  # empty list = allow all
    return user_id in allowed


def _get_selected_instance(user_id: int) -> str:
    """Return the instance name selected by a user (default: this instance)."""
    settings = get_settings()
    return _user_selected_instance.get(user_id, settings.instance_name)


def _is_this_instance(user_id: int) -> bool:
    """True if the user is talking to this instance."""
    settings = get_settings()
    selected = _get_selected_instance(user_id)
    return selected == settings.instance_name


def register_instance(name: str, base_url: str = "") -> None:
    """Register an instance in the in-memory registry."""
    _instance_registry[name] = {
        "base_url": base_url,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }


def get_instances() -> dict[str, dict]:
    """Return the full instance registry."""
    return dict(_instance_registry)


# ---------------------------------------------------------------------------
# RAG helper (non-streaming)
# ---------------------------------------------------------------------------


async def _rag_query(question: str) -> tuple[str, list[dict]]:
    """Run a RAG query and return (answer_text, sources).

    This reuses the existing embedding + qdrant search + ollama pipeline
    but collects the full response instead of streaming.
    """
    from app.config import get_settings
    from app.dependencies import get_qdrant, get_http_client
    from app.services.embedding import embed_text
    from app.utils.prompt_templates import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    settings = get_settings()
    qdrant = await get_qdrant()
    client = await get_http_client()

    query_embedding = await embed_text(question)
    if not query_embedding:
        return "Failed to process your question (embedding error).", []

    query_response = await qdrant.query_points(
        collection_name=settings.qdrant_collection,
        query=query_embedding,
        limit=5,
        score_threshold=0.3,
    )

    doc_chunks: dict[str, dict] = {}
    for hit in query_response.points:
        payload = hit.payload or {}
        doc_id = payload.get("doc_id", "")
        if not doc_id:
            continue
        if doc_id not in doc_chunks or hit.score > doc_chunks[doc_id]["score"]:
            doc_chunks[doc_id] = {
                "score": hit.score,
                "payload": payload,
            }

    sorted_docs = sorted(
        doc_chunks.items(), key=lambda x: x[1]["score"], reverse=True
    )[:3]

    context_parts: list[str] = []
    sources: list[dict] = []

    for doc_id, info in sorted_docs:
        payload = info["payload"]
        full_text = payload.get("full_text", "")

        if not full_text:
            zero_results, _ = await qdrant.scroll(
                collection_name=settings.qdrant_collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        FieldCondition(key="chunk_index", match=MatchValue(value=0)),
                    ]
                ),
                limit=1,
            )
            if zero_results:
                full_text = zero_results[0].payload.get("full_text", "")

        filename = payload.get("filename", "unknown")
        folder = payload.get("folder", "")
        context_parts.append(f"### {filename}\n{full_text[:3000]}")
        sources.append({
            "doc_id": doc_id,
            "filename": filename,
            "folder": folder,
            "score": round(info["score"], 4),
        })

    context_str = (
        "\n\n".join(context_parts) if context_parts else "No relevant documents found."
    )
    user_prompt = RAG_CONTEXT_TEMPLATE.format(context=context_str, question=question)

    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        url = settings.ollama_url + "/api/chat"
        resp = await client.post(
            url,
            json={
                "model": settings.agent_model,
                "messages": messages,
                "stream": False,
                "think": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "No response from model.")
    except Exception as e:
        logger.error("Ollama chat failed: %s", e)
        answer = f"Error communicating with the language model: {e}"

    return answer, sources


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------


async def _list_documents(offset: int = 0, limit: int = PAGE_SIZE) -> tuple[list[dict], int]:
    """Return a page of documents from qdrant."""
    from app.config import get_settings
    from app.dependencies import get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="chunk_index", match=MatchValue(value=0))]
        ),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    total = len(points)
    # Sort by ingested_at descending
    points.sort(
        key=lambda p: (p.payload or {}).get("ingested_at", ""),
        reverse=True,
    )
    page = points[offset : offset + limit]

    docs = []
    for point in page:
        payload = point.payload or {}
        docs.append({
            "doc_id": payload.get("doc_id", ""),
            "filename": payload.get("filename", ""),
            "folder": payload.get("folder", ""),
            "file_type": payload.get("file_type", ""),
            "file_size": payload.get("file_size", 0),
        })

    return docs, total


async def _find_document_by_name(query: str) -> dict | None:
    """Find a document by partial filename match."""
    from app.config import get_settings
    from app.dependencies import get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="chunk_index", match=MatchValue(value=0))]
        ),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    query_lower = query.lower().strip()
    for point in points:
        payload = point.payload or {}
        filename = payload.get("filename", "")
        if query_lower in filename.lower():
            return payload

    return None


async def _get_document_by_id(doc_id: str) -> dict | None:
    """Get a document's payload from qdrant by doc_id."""
    from app.config import get_settings
    from app.dependencies import get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    settings = get_settings()
    qdrant = await get_qdrant()

    points, _ = await qdrant.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="chunk_index", match=MatchValue(value=0)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if points:
        return points[0].payload or {}
    return None


# ---------------------------------------------------------------------------
# Bot command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not _is_user_allowed(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    settings = get_settings()
    await update.message.reply_text(
        f"Welcome to Document Manager Bot!\n\n"
        f"Connected instance: *{settings.instance_name}*\n\n"
        f"Commands:\n"
        f"/search <query> - Search documents\n"
        f"/ask <question> - Ask about your documents\n"
        f"/list - List recent documents\n"
        f"/send <filename> - Get a document file\n"
        f"/rename <doc\\_id> - AI rename suggestion\n"
        f"/select - Choose which instance to use\n"
        f"/help - Show this help",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not _is_user_allowed(update.effective_user.id):
        return

    settings = get_settings()
    selected = _get_selected_instance(update.effective_user.id)
    await update.message.reply_text(
        f"*Document Manager Bot*\n"
        f"Active instance: *{selected}*\n\n"
        f"*Commands:*\n"
        f"/search <query> - Search documents via RAG\n"
        f"/ask <question> - Ask a question about your documents\n"
        f"/list - List recent documents (paginated)\n"
        f"/send <filename> - Send a document file to you\n"
        f"/rename <doc\\_id> - Get AI rename suggestion\n"
        f"/select - Choose which instance to talk to\n"
        f"/help - Show this message",
        parse_mode="Markdown",
    )


async def cmd_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /select command - show available instances."""
    if not _is_user_allowed(update.effective_user.id):
        return

    settings = get_settings()
    # Ensure this instance is registered
    register_instance(settings.instance_name)

    if not _instance_registry:
        await update.message.reply_text("No instances registered.")
        return

    current = _get_selected_instance(update.effective_user.id)
    buttons = []
    for name, info in _instance_registry.items():
        label = f"{'>> ' if name == current else ''}{name}"
        last_seen = info.get("last_seen", "")
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"select_instance:{name}")]
        )

    await update.message.reply_text(
        "Select an instance:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_select_instance(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle instance selection callback."""
    query = update.callback_query
    if not _is_user_allowed(query.from_user.id):
        return

    await query.answer()
    data = query.data or ""
    if not data.startswith("select_instance:"):
        return

    instance_name = data.split(":", 1)[1]
    _user_selected_instance[query.from_user.id] = instance_name
    await query.edit_message_text(f"Selected instance: *{instance_name}*", parse_mode="Markdown")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search <query> command."""
    if not _is_user_allowed(update.effective_user.id):
        return

    if not _is_this_instance(update.effective_user.id):
        await update.message.reply_text(
            f"This command is for instance *{_get_selected_instance(update.effective_user.id)}*, "
            f"but you are connected to *{get_settings().instance_name}*. "
            f"Use /select to switch.",
            parse_mode="Markdown",
        )
        return

    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /search <query>")
        return

    msg = await update.message.reply_text("Searching...")

    try:
        answer, sources = await _rag_query(query_text)

        source_text = ""
        if sources:
            source_lines = []
            for s in sources:
                folder = s.get("folder", "")
                prefix = f"{folder}/" if folder else ""
                source_lines.append(f"  - {prefix}{s['filename']} (score: {s['score']})")
            source_text = "\n*Sources:*\n" + "\n".join(source_lines)

        # Telegram message limit is 4096 chars
        full_text = f"{answer}{source_text}"
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "\n..."

        await msg.edit_text(full_text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Search command failed: %s", e)
        await msg.edit_text(f"Search failed: {e}")


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ask <question> command (alias for search)."""
    await cmd_search(update, context)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command - list documents with pagination."""
    if not _is_user_allowed(update.effective_user.id):
        return

    if not _is_this_instance(update.effective_user.id):
        await update.message.reply_text(
            f"This command is for instance *{_get_selected_instance(update.effective_user.id)}*, "
            f"but you are connected to *{get_settings().instance_name}*.",
            parse_mode="Markdown",
        )
        return

    _user_list_offset[update.effective_user.id] = 0
    await _send_document_list(update.message, update.effective_user.id, 0)


async def _send_document_list(message_or_query, user_id: int, offset: int) -> None:
    """Build and send/edit a paginated document list."""
    docs, total = await _list_documents(offset=offset, limit=PAGE_SIZE)

    if total == 0:
        text = "No documents found."
        if hasattr(message_or_query, "edit_text"):
            await message_or_query.edit_message_text(text)
        else:
            await message_or_query.reply_text(text)
        return

    lines = [f"*Documents* ({offset + 1}-{min(offset + PAGE_SIZE, total)} of {total}):\n"]
    for i, doc in enumerate(docs, start=offset + 1):
        folder = doc.get("folder", "")
        prefix = f"{folder}/" if folder else ""
        size_kb = (doc.get("file_size", 0) or 0) / 1024
        lines.append(f"{i}. `{prefix}{doc['filename']}` ({size_kb:.0f}KB)")
        lines.append(f"   ID: `{doc['doc_id'][:12]}...`")

    buttons = []
    row = []
    if offset > 0:
        row.append(InlineKeyboardButton("< Prev", callback_data=f"list_page:{offset - PAGE_SIZE}"))
    if offset + PAGE_SIZE < total:
        row.append(InlineKeyboardButton("Next >", callback_data=f"list_page:{offset + PAGE_SIZE}"))
    if row:
        buttons.append(row)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    if hasattr(message_or_query, "edit_message_text"):
        await message_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await message_or_query.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def callback_list_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle list pagination callback."""
    query = update.callback_query
    if not _is_user_allowed(query.from_user.id):
        return

    await query.answer()
    data = query.data or ""
    if not data.startswith("list_page:"):
        return

    offset = int(data.split(":", 1)[1])
    offset = max(0, offset)
    _user_list_offset[query.from_user.id] = offset
    await _send_document_list(query, query.from_user.id, offset)


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /send <filename> command - send a document file."""
    if not _is_user_allowed(update.effective_user.id):
        return

    if not _is_this_instance(update.effective_user.id):
        await update.message.reply_text(
            f"This command is for instance *{_get_selected_instance(update.effective_user.id)}*, "
            f"but you are connected to *{get_settings().instance_name}*.",
            parse_mode="Markdown",
        )
        return

    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /send <filename or doc_id>")
        return

    msg = await update.message.reply_text("Looking for document...")

    # Try to find by doc_id first, then by filename
    doc = await _get_document_by_id(query_text)
    if not doc:
        doc = await _find_document_by_name(query_text)

    if not doc:
        await msg.edit_text(f"Document not found: {query_text}")
        return

    file_path = doc.get("file_path", "")
    filename = doc.get("filename", "document")

    if not file_path or not os.path.exists(file_path):
        await msg.edit_text(f"File not found on disk for: {filename}")
        return

    try:
        await msg.edit_text(f"Sending *{filename}*...", parse_mode="Markdown")
        with open(file_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"From: {doc.get('folder', 'unsorted')}/{filename}",
            )
        await msg.delete()
    except Exception as e:
        logger.error("Failed to send document: %s", e)
        await msg.edit_text(f"Failed to send document: {e}")


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rename <doc_id> command - suggest AI rename."""
    if not _is_user_allowed(update.effective_user.id):
        return

    if not _is_this_instance(update.effective_user.id):
        await update.message.reply_text(
            f"This command is for instance *{_get_selected_instance(update.effective_user.id)}*, "
            f"but you are connected to *{get_settings().instance_name}*.",
            parse_mode="Markdown",
        )
        return

    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /rename <doc\\_id or filename>")
        return

    msg = await update.message.reply_text("Analyzing document...")

    # Find the document
    doc = await _get_document_by_id(query_text)
    if not doc:
        doc = await _find_document_by_name(query_text)

    if not doc:
        await msg.edit_text(f"Document not found: {query_text}")
        return

    doc_id = doc.get("doc_id", "")
    current_name = doc.get("filename", "")
    full_text = doc.get("full_text", "") or doc.get("chunk_text", "")

    try:
        from app.services.renaming import suggest_rename

        result = await suggest_rename(doc_id, full_text, current_name)
        suggested = result.suggested_name

        buttons = [
            [
                InlineKeyboardButton(
                    "Apply", callback_data=f"rename_apply:{doc_id}:{suggested}"
                ),
                InlineKeyboardButton("Cancel", callback_data="rename_cancel"),
            ]
        ]

        await msg.edit_text(
            f"*Current:* `{current_name}`\n"
            f"*Suggested:* `{suggested}`\n\n"
            f"Apply this rename?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logger.error("Rename suggestion failed: %s", e)
        await msg.edit_text(f"Rename suggestion failed: {e}")


async def callback_rename(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle rename apply/cancel callbacks."""
    query = update.callback_query
    if not _is_user_allowed(query.from_user.id):
        return

    await query.answer()
    data = query.data or ""

    if data == "rename_cancel":
        await query.edit_message_text("Rename cancelled.")
        return

    if data.startswith("rename_apply:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.edit_message_text("Invalid rename data.")
            return

        doc_id = parts[1]
        new_name = parts[2]

        try:
            from app.services.renaming import apply_rename

            new_path = await apply_rename(doc_id, new_name)
            new_filename = os.path.basename(new_path)
            await query.edit_message_text(
                f"Renamed to: *{new_filename}*", parse_mode="Markdown"
            )
        except Exception as e:
            logger.error("Rename apply failed: %s", e)
            await query.edit_message_text(f"Rename failed: {e}")


async def handle_plain_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle plain text messages as implicit /ask."""
    if not _is_user_allowed(update.effective_user.id):
        return

    if not _is_this_instance(update.effective_user.id):
        settings = get_settings()
        await update.message.reply_text(
            f"Instance *{settings.instance_name}* received your message, "
            f"but you selected *{_get_selected_instance(update.effective_user.id)}*. "
            f"Use /select to switch.",
            parse_mode="Markdown",
        )
        return

    # Treat plain messages as search/ask queries
    question = update.message.text or ""
    if not question.strip():
        return

    msg = await update.message.reply_text("Thinking...")

    try:
        answer, sources = await _rag_query(question)

        source_text = ""
        if sources:
            source_lines = [
                f"  - {s.get('folder', '')}/{s['filename']}"
                for s in sources
            ]
            source_text = "\n\n_Sources:_\n" + "\n".join(source_lines)

        full_text = f"{answer}{source_text}"
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "\n..."

        await msg.edit_text(full_text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Message handling failed: %s", e)
        await msg.edit_text(f"Error: {e}")


# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------


async def start_bot() -> None:
    """Initialize and start the Telegram bot (polling mode)."""
    global _application, _bot_running

    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN not set, skipping bot startup.")
        return

    if _bot_running:
        logger.warning("Telegram bot already running.")
        return

    if not settings.telegram_bot_allowed_user_ids:
        logger.warning(
            "TELEGRAM_BOT_ALLOWED_USERS is empty - bot will accept messages from ALL users!"
        )

    # Register this instance
    register_instance(settings.instance_name)

    # Build the application
    _application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # Register handlers
    _application.add_handler(CommandHandler("start", cmd_start))
    _application.add_handler(CommandHandler("help", cmd_help))
    _application.add_handler(CommandHandler("select", cmd_select))
    _application.add_handler(CommandHandler("search", cmd_search))
    _application.add_handler(CommandHandler("ask", cmd_ask))
    _application.add_handler(CommandHandler("list", cmd_list))
    _application.add_handler(CommandHandler("send", cmd_send))
    _application.add_handler(CommandHandler("rename", cmd_rename))

    # Callback query handlers
    _application.add_handler(
        CallbackQueryHandler(callback_select_instance, pattern=r"^select_instance:")
    )
    _application.add_handler(
        CallbackQueryHandler(callback_list_page, pattern=r"^list_page:")
    )
    _application.add_handler(
        CallbackQueryHandler(callback_rename, pattern=r"^rename_")
    )

    # Plain text messages -> implicit ask
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_message)
    )

    # Set bot commands for the menu
    await _application.initialize()
    await _application.bot.set_my_commands([
        BotCommand("search", "Search documents"),
        BotCommand("ask", "Ask about documents"),
        BotCommand("list", "List recent documents"),
        BotCommand("send", "Send a document file"),
        BotCommand("rename", "AI rename suggestion"),
        BotCommand("select", "Choose instance"),
        BotCommand("help", "Show help"),
    ])

    # Start polling in the background
    await _application.start()
    await _application.updater.start_polling(drop_pending_updates=True)

    _bot_running = True
    logger.info(
        "Telegram bot started (instance: %s, allowed users: %s)",
        settings.instance_name,
        settings.telegram_bot_allowed_user_ids or "ALL",
    )


async def stop_bot() -> None:
    """Stop the Telegram bot gracefully."""
    global _application, _bot_running

    if not _bot_running or _application is None:
        return

    try:
        await _application.updater.stop()
        await _application.stop()
        await _application.shutdown()
    except Exception as e:
        logger.error("Error stopping Telegram bot: %s", e)

    _bot_running = False
    _application = None
    logger.info("Telegram bot stopped.")


def is_bot_running() -> bool:
    """Check if the bot is currently running."""
    return _bot_running
