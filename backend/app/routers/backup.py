import logging

from fastapi import APIRouter, HTTPException

from app.services.backup import trigger_snapshot, list_snapshots

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/snapshot")
async def create_snapshot():
    """Trigger a manual Qdrant snapshot."""
    try:
        result = await trigger_snapshot()
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Snapshot creation failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Snapshot endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots")
async def get_snapshots():
    """List all available local snapshots."""
    try:
        snapshots = list_snapshots()
        return {"snapshots": snapshots, "total": len(snapshots)}
    except Exception as e:
        logger.error("List snapshots error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
