"""Router for Telegram Bot status and instance management."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services.telegram_bot import (
    is_bot_running,
    register_instance,
    get_instances,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class InstanceRegistration(BaseModel):
    instance_name: str
    base_url: str = ""


class InstanceInfo(BaseModel):
    instance_name: str
    base_url: str = ""
    last_seen: str = ""
    is_current: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def bot_status():
    """Return the current Telegram bot status."""
    settings = get_settings()
    return {
        "running": is_bot_running(),
        "instance_name": settings.instance_name,
        "token_configured": bool(settings.telegram_bot_token),
        "allowed_users": settings.telegram_bot_allowed_user_ids,
    }


@router.post("/register-instance")
async def register_bot_instance(body: InstanceRegistration):
    """Register a remote instance (called by other instances)."""
    register_instance(body.instance_name, body.base_url)
    logger.info("Registered instance: %s", body.instance_name)
    return {"status": "ok", "instance_name": body.instance_name}


@router.get("/instances")
async def list_instances():
    """List all registered instances."""
    settings = get_settings()
    instances = get_instances()
    result = []
    for name, info in instances.items():
        result.append(
            InstanceInfo(
                instance_name=name,
                base_url=info.get("base_url", ""),
                last_seen=info.get("last_seen", ""),
                is_current=(name == settings.instance_name),
            )
        )
    return {"instances": [i.model_dump() for i in result]}
