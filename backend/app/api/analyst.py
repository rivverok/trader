"""API routes for analyst input CRUD."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analyst_input import AnalystInput
from app.models.stock import Stock

router = APIRouter(prefix="/api/analyst", tags=["analyst"])


# ── Schemas ──────────────────────────────────────────────────────────


class AnalystInputCreate(BaseModel):
    symbol: str
    thesis: str
    conviction: int = Field(ge=1, le=10)
    time_horizon_days: int | None = None
    catalysts: str | None = None
    override_flag: str = Field(default="none", pattern="^(none|avoid|boost)$")


class AnalystInputUpdate(BaseModel):
    thesis: str | None = None
    conviction: int | None = Field(default=None, ge=1, le=10)
    time_horizon_days: int | None = None
    catalysts: str | None = None
    override_flag: str | None = Field(default=None, pattern="^(none|avoid|boost)$")
    is_active: bool | None = None


class AnalystInputResponse(BaseModel):
    id: int
    stock_id: int
    symbol: str
    thesis: str
    conviction: int
    time_horizon_days: int | None
    catalysts: str | None
    override_flag: str
    is_active: bool
    created_at: str
    updated_at: str


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/input", response_model=AnalystInputResponse)
async def create_analyst_input(
    body: AnalystInputCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit a new analyst input for a stock."""
    result = await db.execute(
        select(Stock).where(Stock.symbol == body.symbol.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"Stock {body.symbol} not found")

    inp = AnalystInput(
        stock_id=stock.id,
        thesis=body.thesis,
        conviction=body.conviction,
        time_horizon_days=body.time_horizon_days,
        catalysts=body.catalysts,
        override_flag=body.override_flag,
    )
    db.add(inp)
    await db.commit()
    await db.refresh(inp)

    return _to_response(inp, stock.symbol)


@router.get("/inputs", response_model=list[AnalystInputResponse])
async def list_analyst_inputs(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """List all analyst inputs (active by default)."""
    query = (
        select(AnalystInput, Stock.symbol)
        .join(Stock, Stock.id == AnalystInput.stock_id)
    )
    if active_only:
        query = query.where(AnalystInput.is_active.is_(True))
    query = query.order_by(desc(AnalystInput.updated_at))

    result = await db.execute(query)
    rows = result.all()
    return [_to_response(inp, sym) for inp, sym in rows]


@router.put("/input/{input_id}", response_model=AnalystInputResponse)
async def update_analyst_input(
    input_id: int,
    body: AnalystInputUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing analyst input."""
    result = await db.execute(
        select(AnalystInput).where(AnalystInput.id == input_id)
    )
    inp = result.scalar_one_or_none()
    if not inp:
        raise HTTPException(404, detail="Analyst input not found")

    if body.thesis is not None:
        inp.thesis = body.thesis
    if body.conviction is not None:
        inp.conviction = body.conviction
    if body.time_horizon_days is not None:
        inp.time_horizon_days = body.time_horizon_days
    if body.catalysts is not None:
        inp.catalysts = body.catalysts
    if body.override_flag is not None:
        inp.override_flag = body.override_flag
    if body.is_active is not None:
        inp.is_active = body.is_active

    inp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(inp)

    # Get symbol
    result = await db.execute(select(Stock.symbol).where(Stock.id == inp.stock_id))
    symbol = result.scalar_one()

    return _to_response(inp, symbol)


@router.delete("/input/{input_id}")
async def delete_analyst_input(
    input_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an analyst input."""
    result = await db.execute(
        select(AnalystInput).where(AnalystInput.id == input_id)
    )
    inp = result.scalar_one_or_none()
    if not inp:
        raise HTTPException(404, detail="Analyst input not found")

    await db.delete(inp)
    await db.commit()
    return {"status": "deleted", "id": input_id}


# ── Helpers ──────────────────────────────────────────────────────────


def _to_response(inp: AnalystInput, symbol: str) -> AnalystInputResponse:
    return AnalystInputResponse(
        id=inp.id,
        stock_id=inp.stock_id,
        symbol=symbol,
        thesis=inp.thesis,
        conviction=inp.conviction,
        time_horizon_days=inp.time_horizon_days,
        catalysts=inp.catalysts,
        override_flag=inp.override_flag,
        is_active=inp.is_active,
        created_at=inp.created_at.isoformat(),
        updated_at=inp.updated_at.isoformat(),
    )
