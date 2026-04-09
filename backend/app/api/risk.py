"""API routes for risk status, config, signal weights, and resume."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio import PortfolioPosition, PortfolioSnapshot
from app.models.risk import RiskState
from app.models.stock import Stock

router = APIRouter(prefix="/api", tags=["risk", "config"])


# ── Schemas ──────────────────────────────────────────────────────────


class RiskStatusResponse(BaseModel):
    trading_halted: bool
    halt_reason: str | None
    halted_at: str | None
    daily_realized_loss: float
    portfolio_peak_value: float
    current_drawdown_pct: float
    # Config
    max_trade_dollars: float
    max_position_pct: float
    max_sector_pct: float
    daily_loss_limit: float
    max_drawdown_pct: float
    min_confidence: float
    # Exposure
    total_position_value: float
    positions_count: int
    sector_exposure: dict[str, float]


class RiskConfigUpdate(BaseModel):
    max_trade_dollars: float | None = Field(default=None, gt=0)
    max_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_sector_pct: float | None = Field(default=None, gt=0, le=100)
    daily_loss_limit: float | None = Field(default=None, gt=0)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    min_confidence: float | None = Field(default=None, ge=0, le=1)


class WeightsResponse(BaseModel):
    ml: float
    claude: float
    analyst: float


class WeightsUpdate(BaseModel):
    ml: float = Field(ge=0, le=1)
    claude: float = Field(ge=0, le=1)
    analyst: float = Field(ge=0, le=1)


# ── Risk endpoints ───────────────────────────────────────────────────


@router.get("/risk/status", response_model=RiskStatusResponse)
async def get_risk_status(db: AsyncSession = Depends(get_db)):
    """Current risk state: drawdown, daily loss, exposure, config, circuit breakers."""
    state = await _get_state(db)

    # Portfolio value
    snap_result = await db.execute(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(1)
    )
    snap = snap_result.scalar_one_or_none()
    current_value = snap.total_value if snap else state.portfolio_peak_value

    drawdown = 0.0
    if state.portfolio_peak_value > 0:
        drawdown = ((state.portfolio_peak_value - current_value) / state.portfolio_peak_value) * 100

    # Position exposure
    pos_result = await db.execute(select(PortfolioPosition))
    positions = list(pos_result.scalars().all())
    total_pos_value = sum(p.current_value for p in positions)

    # Sector exposure
    sector_exposure: dict[str, float] = {}
    if positions:
        stock_ids = [p.stock_id for p in positions]
        stock_result = await db.execute(
            select(Stock).where(Stock.id.in_(stock_ids))
        )
        stock_map = {s.id: s for s in stock_result.scalars().all()}
        for p in positions:
            s = stock_map.get(p.stock_id)
            sector = s.sector if s and s.sector else "Unknown"
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + p.current_value

    return RiskStatusResponse(
        trading_halted=state.trading_halted,
        halt_reason=state.halt_reason,
        halted_at=state.halted_at.isoformat() if state.halted_at else None,
        daily_realized_loss=state.daily_realized_loss,
        portfolio_peak_value=state.portfolio_peak_value,
        current_drawdown_pct=round(drawdown, 2),
        max_trade_dollars=state.max_trade_dollars,
        max_position_pct=state.max_position_pct,
        max_sector_pct=state.max_sector_pct,
        daily_loss_limit=state.daily_loss_limit,
        max_drawdown_pct=state.max_drawdown_pct,
        min_confidence=state.min_confidence,
        total_position_value=total_pos_value,
        positions_count=len(positions),
        sector_exposure=sector_exposure,
    )


@router.put("/risk/config")
async def update_risk_config(
    body: RiskConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update risk parameters. Only user can change these."""
    state = await _get_state(db)
    if body.max_trade_dollars is not None:
        state.max_trade_dollars = body.max_trade_dollars
    if body.max_position_pct is not None:
        state.max_position_pct = body.max_position_pct
    if body.max_sector_pct is not None:
        state.max_sector_pct = body.max_sector_pct
    if body.daily_loss_limit is not None:
        state.daily_loss_limit = body.daily_loss_limit
    if body.max_drawdown_pct is not None:
        state.max_drawdown_pct = body.max_drawdown_pct
    if body.min_confidence is not None:
        state.min_confidence = body.min_confidence
    await db.commit()
    return {"status": "updated"}


@router.post("/risk/resume")
async def resume_trading(db: AsyncSession = Depends(get_db)):
    """Clear trading_halted flag — USER ACTION ONLY."""
    state = await _get_state(db)
    state.trading_halted = False
    state.halt_reason = None
    state.halted_at = None
    await db.commit()
    return {"status": "resumed"}


# ── Signal weight endpoints ──────────────────────────────────────────


@router.get("/config/weights", response_model=WeightsResponse)
async def get_weights():
    """Get current signal weights."""
    from app.config import settings
    return WeightsResponse(
        ml=settings.SIGNAL_WEIGHT_ML,
        claude=settings.SIGNAL_WEIGHT_CLAUDE,
        analyst=settings.SIGNAL_WEIGHT_ANALYST,
    )


@router.put("/config/weights", response_model=WeightsResponse)
async def update_weights(body: WeightsUpdate):
    """Update signal weights (runtime only — persists until restart).

    For permanent changes, update .env file.
    """
    from app.config import settings
    # Normalize so they sum to 1.0
    total = body.ml + body.claude + body.analyst
    if total <= 0:
        from fastapi import HTTPException
        raise HTTPException(400, "Weights must sum to > 0")

    settings.SIGNAL_WEIGHT_ML = body.ml / total
    settings.SIGNAL_WEIGHT_CLAUDE = body.claude / total
    settings.SIGNAL_WEIGHT_ANALYST = body.analyst / total

    return WeightsResponse(
        ml=settings.SIGNAL_WEIGHT_ML,
        claude=settings.SIGNAL_WEIGHT_CLAUDE,
        analyst=settings.SIGNAL_WEIGHT_ANALYST,
    )


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_state(db: AsyncSession) -> RiskState:
    result = await db.execute(select(RiskState).where(RiskState.id == 1))
    state = result.scalar_one_or_none()
    if not state:
        state = RiskState(id=1)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state
