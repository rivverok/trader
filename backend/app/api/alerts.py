"""API routes for alerts — list, acknowledge, WebSocket stream."""

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.engine.alert_service import register_ws, unregister_ws
from app.models.alert import Alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Schemas ──────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: int
    type: str
    severity: str
    message: str
    acknowledged: bool
    created_at: str

    class Config:
        from_attributes = True


# ── REST Endpoints ───────────────────────────────────────────────────

@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List alerts, newest first."""
    query = select(Alert)
    if unread_only:
        query = query.where(Alert.acknowledged == False)
    query = query.order_by(desc(Alert.created_at)).limit(limit)

    result = await db.execute(query)
    return [
        AlertResponse(
            id=a.id,
            type=a.type,
            severity=a.severity,
            message=a.message,
            acknowledged=a.acknowledged,
            created_at=a.created_at.isoformat(),
        )
        for a in result.scalars().all()
    ]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as acknowledged."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    await db.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


@router.post("/acknowledge-all")
async def acknowledge_all_alerts(db: AsyncSession = Depends(get_db)):
    """Mark all unread alerts as acknowledged."""
    await db.execute(
        update(Alert).where(Alert.acknowledged == False).values(acknowledged=True)
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db)):
    """Get count of unread alerts (for badge)."""
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Alert.id)).where(Alert.acknowledged == False)
    )
    return {"count": result.scalar_one()}


# ── WebSocket ────────────────────────────────────────────────────────

@router.websocket("/ws")
async def alerts_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time alert push to frontend."""
    await websocket.accept()
    register_ws(websocket)
    try:
        while True:
            # Keep connection alive — client sends pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws(websocket)
