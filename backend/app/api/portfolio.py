"""API routes for portfolio and trade history."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.portfolio_sync import get_portfolio_summary, get_portfolio_history
from app.models.stock import Stock
from app.models.trade import Trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ── Schemas ──────────────────────────────────────────────────────────

class PositionResponse(BaseModel):
    stock_id: int
    symbol: str
    shares: float
    avg_cost_basis: float
    current_value: float
    unrealized_pnl: float
    realized_pnl: float


class PortfolioResponse(BaseModel):
    total_value: float
    cash: float
    positions_value: float
    daily_pnl: float
    cumulative_pnl: float
    buying_power: float
    positions: list[PositionResponse]
    account_status: str


class SnapshotResponse(BaseModel):
    timestamp: str
    total_value: float
    cash: float
    positions_value: float
    daily_pnl: float
    cumulative_pnl: float


class TradeResponse(BaseModel):
    id: int
    stock_id: int
    symbol: str
    proposed_trade_id: int | None
    action: str
    shares: float
    price: float
    order_type: str
    fill_price: float | None
    fill_time: str | None
    slippage: float | None
    commission: float | None
    alpaca_order_id: str | None
    status: str
    created_at: str


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=PortfolioResponse)
async def get_portfolio(db: AsyncSession = Depends(get_db)):
    """Get current portfolio — positions, cash, P&L."""
    summary = await get_portfolio_summary(db)
    return PortfolioResponse(
        total_value=summary["total_value"],
        cash=summary["cash"],
        positions_value=summary["positions_value"],
        daily_pnl=summary["daily_pnl"],
        cumulative_pnl=summary["cumulative_pnl"],
        buying_power=summary["buying_power"],
        positions=[PositionResponse(**p) for p in summary["positions"]],
        account_status=summary["account_status"],
    )


@router.get("/history", response_model=list[SnapshotResponse])
async def portfolio_history(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio snapshots for charting."""
    history = await get_portfolio_history(db, days)
    return [SnapshotResponse(**s) for s in history]


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get executed trade history."""
    query = (
        select(Trade, Stock.symbol)
        .join(Stock, Stock.id == Trade.stock_id)
    )
    if status:
        query = query.where(Trade.status == status)
    query = query.order_by(desc(Trade.created_at)).limit(limit)

    result = await db.execute(query)
    return [
        TradeResponse(
            id=t.id,
            stock_id=t.stock_id,
            symbol=sym,
            proposed_trade_id=t.proposed_trade_id,
            action=t.action,
            shares=t.shares,
            price=t.price,
            order_type=t.order_type,
            fill_price=t.fill_price,
            fill_time=t.fill_time.isoformat() if t.fill_time else None,
            slippage=t.slippage,
            commission=t.commission,
            alpaca_order_id=t.alpaca_order_id,
            status=t.status,
            created_at=t.created_at.isoformat(),
        )
        for t, sym in result.all()
    ]
