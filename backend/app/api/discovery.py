"""API routes for AI stock discovery — hints, logs, and manual triggers."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.discovery import DiscoveryLog, WatchlistHint

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


# ── Schemas ──────────────────────────────────────────────────────────


class HintCreate(BaseModel):
    hint_text: str
    symbol: str | None = None


class HintResponse(BaseModel):
    id: int
    hint_text: str
    symbol: str | None
    status: str
    ai_response: str | None
    created_at: str

    model_config = {"from_attributes": True}


class DiscoveryLogResponse(BaseModel):
    id: int
    batch_id: str
    action: str
    symbol: str
    reasoning: str
    confidence: float
    source: str
    created_at: str

    model_config = {"from_attributes": True}


class DiscoveryStatusResponse(BaseModel):
    last_run: str | None
    last_result: dict


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/log", response_model=list[DiscoveryLogResponse])
async def get_discovery_log(
    limit: int = Query(50, le=200),
    symbol: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get the AI discovery decision log."""
    query = select(DiscoveryLog).order_by(desc(DiscoveryLog.created_at)).limit(limit)
    if symbol:
        query = query.where(DiscoveryLog.symbol == symbol.upper())
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        DiscoveryLogResponse(
            id=log.id,
            batch_id=log.batch_id,
            action=log.action,
            symbol=log.symbol,
            reasoning=log.reasoning,
            confidence=log.confidence,
            source=log.source,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post("/hints", response_model=HintResponse, status_code=201)
async def create_hint(payload: HintCreate, db: AsyncSession = Depends(get_db)):
    """Submit a hint for the AI to consider during the next discovery run."""
    hint = WatchlistHint(
        hint_text=payload.hint_text.strip(),
        symbol=payload.symbol.upper().strip() if payload.symbol else None,
        status="pending",
    )
    db.add(hint)
    await db.commit()
    await db.refresh(hint)
    return HintResponse(
        id=hint.id,
        hint_text=hint.hint_text,
        symbol=hint.symbol,
        status=hint.status,
        ai_response=hint.ai_response,
        created_at=hint.created_at.isoformat(),
    )


@router.get("/hints", response_model=list[HintResponse])
async def list_hints(
    status: Optional[str] = Query(None, description="Filter: pending, considered"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List user hints, optionally filtered by status."""
    query = select(WatchlistHint).order_by(desc(WatchlistHint.created_at)).limit(limit)
    if status:
        query = query.where(WatchlistHint.status == status)
    result = await db.execute(query)
    hints = result.scalars().all()
    return [
        HintResponse(
            id=h.id,
            hint_text=h.hint_text,
            symbol=h.symbol,
            status=h.status,
            ai_response=h.ai_response,
            created_at=h.created_at.isoformat(),
        )
        for h in hints
    ]


@router.post("/trigger")
async def trigger_discovery():
    """Manually trigger a stock discovery cycle."""
    from app.tasks.discovery_tasks import discover_stocks

    task = discover_stocks.delay(force=True)
    return {"task_id": task.id, "task_name": "discover_stocks"}


@router.get("/status", response_model=DiscoveryStatusResponse)
async def discovery_status():
    """Get the status of the last discovery run."""
    from app.tasks.discovery_tasks import get_discovery_status

    status = get_discovery_status()
    return DiscoveryStatusResponse(
        last_run=status.get("last_run"),
        last_result=status.get("last_result", {}),
    )
