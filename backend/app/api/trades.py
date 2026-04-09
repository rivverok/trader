"""API routes for proposed trades — view, approve, reject."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.stock import Stock
from app.models.trade import ProposedTrade

router = APIRouter(prefix="/api/trades", tags=["trades"])


# ── Schemas ──────────────────────────────────────────────────────────


class ProposedTradeResponse(BaseModel):
    id: int
    stock_id: int
    symbol: str
    action: str
    shares: float
    price_target: float | None
    order_type: str
    ml_signal_id: int | None
    synthesis_id: int | None
    analyst_input_id: int | None
    confidence: float
    reasoning_chain: str | None
    risk_check_passed: bool | None
    risk_check_reason: str | None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class RejectBody(BaseModel):
    reason: str = "Manually rejected by user"


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/proposed", response_model=list[ProposedTradeResponse])
async def list_proposed_trades(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List proposed trades with full reasoning."""
    query = (
        select(ProposedTrade, Stock.symbol)
        .join(Stock, Stock.id == ProposedTrade.stock_id)
    )
    if status:
        query = query.where(ProposedTrade.status == status)
    query = query.order_by(desc(ProposedTrade.created_at)).limit(limit)

    result = await db.execute(query)
    rows = result.all()
    return [_to_response(t, sym) for t, sym in rows]


@router.post("/{trade_id}/approve")
async def approve_trade(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Manually approve a proposed trade (for Stage 5 testing)."""
    result = await db.execute(
        select(ProposedTrade).where(ProposedTrade.id == trade_id)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(404, detail="Trade not found")
    if trade.status != "proposed":
        raise HTTPException(400, detail=f"Trade is already {trade.status}")

    trade.status = "approved"
    trade.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "approved", "trade_id": trade_id}


@router.post("/{trade_id}/reject")
async def reject_trade(
    trade_id: int,
    body: RejectBody | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a proposed trade with reason."""
    result = await db.execute(
        select(ProposedTrade).where(ProposedTrade.id == trade_id)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(404, detail="Trade not found")
    if trade.status not in ("proposed", "approved"):
        raise HTTPException(400, detail=f"Trade is already {trade.status}")

    trade.status = "rejected"
    if body and body.reason:
        trade.risk_check_reason = body.reason
    trade.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "rejected", "trade_id": trade_id}


# ── Helpers ──────────────────────────────────────────────────────────


def _to_response(trade: ProposedTrade, symbol: str) -> ProposedTradeResponse:
    return ProposedTradeResponse(
        id=trade.id,
        stock_id=trade.stock_id,
        symbol=symbol,
        action=trade.action,
        shares=trade.shares,
        price_target=trade.price_target,
        order_type=trade.order_type,
        ml_signal_id=trade.ml_signal_id,
        synthesis_id=trade.synthesis_id,
        analyst_input_id=trade.analyst_input_id,
        confidence=trade.confidence,
        reasoning_chain=trade.reasoning_chain,
        risk_check_passed=trade.risk_check_passed,
        risk_check_reason=trade.risk_check_reason,
        status=trade.status,
        created_at=trade.created_at.isoformat(),
    )
