"""Portfolio sync — keeps local DB in sync with Alpaca as source of truth.

Syncs positions, cash, and portfolio snapshots every 5 minutes.
Calculates P&L and updates risk manager peak values.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.executor import get_account_info, get_alpaca_positions
from app.engine.risk_manager import update_portfolio_peak
from app.models.portfolio import PortfolioPosition, PortfolioSnapshot
from app.models.stock import Stock

logger = logging.getLogger(__name__)


async def sync_portfolio(db: AsyncSession) -> dict:
    """Sync local portfolio state from Alpaca (source of truth).

    Returns a summary dict with totals.
    """
    account = await get_account_info()
    if not account:
        logger.error("Cannot sync portfolio — Alpaca account info unavailable")
        return {"error": "Account info unavailable"}

    alpaca_positions = await get_alpaca_positions()

    cash = account.get("cash", 0.0)
    portfolio_value = account.get("portfolio_value", 0.0)
    equity = account.get("equity", 0.0)

    # Build a set of symbols from Alpaca
    alpaca_symbols = {p["symbol"] for p in alpaca_positions}

    # Get stock lookup: symbol → id
    result = await db.execute(select(Stock))
    stocks = {s.symbol: s.id for s in result.scalars().all()}

    # Remove positions that no longer exist on Alpaca
    result = await db.execute(select(PortfolioPosition))
    existing_positions = result.scalars().all()
    existing_stock_ids = set()
    for pos in existing_positions:
        # Look up symbol for this stock_id
        sym_result = await db.execute(select(Stock.symbol).where(Stock.id == pos.stock_id))
        sym = sym_result.scalar_one_or_none()
        if sym and sym not in alpaca_symbols:
            await db.delete(pos)
        else:
            existing_stock_ids.add(pos.stock_id)

    # Upsert positions from Alpaca
    positions_value = 0.0
    daily_pnl = 0.0
    synced_count = 0

    for ap in alpaca_positions:
        symbol = ap["symbol"]
        stock_id = stocks.get(symbol)

        if not stock_id:
            # Auto-create stock if it exists in Alpaca but not our DB
            new_stock = Stock(symbol=symbol, on_watchlist=False)
            db.add(new_stock)
            await db.flush()
            stock_id = new_stock.id
            stocks[symbol] = stock_id

        market_value = ap.get("market_value", 0.0)
        unrealized_pl = ap.get("unrealized_pl", 0.0)
        positions_value += market_value
        daily_pnl += unrealized_pl

        result = await db.execute(
            select(PortfolioPosition).where(PortfolioPosition.stock_id == stock_id)
        )
        pos = result.scalar_one_or_none()

        if pos:
            pos.shares = ap["qty"]
            pos.avg_cost_basis = ap["avg_entry_price"]
            pos.current_value = market_value
            pos.unrealized_pnl = unrealized_pl
            pos.updated_at = datetime.now(timezone.utc)
        else:
            pos = PortfolioPosition(
                stock_id=stock_id,
                shares=ap["qty"],
                avg_cost_basis=ap["avg_entry_price"],
                current_value=market_value,
                unrealized_pnl=unrealized_pl,
                realized_pnl=0.0,
            )
            db.add(pos)

        synced_count += 1

    # Take a snapshot
    # Calculate cumulative P&L from the last snapshot or start at 0
    last_snap_result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    last_snap = last_snap_result.scalar_one_or_none()
    prev_cumulative = last_snap.cumulative_pnl if last_snap else 0.0
    prev_value = last_snap.total_value if last_snap else portfolio_value
    snapshot_daily_pnl = portfolio_value - prev_value

    snapshot = PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        total_value=portfolio_value,
        cash=cash,
        positions_value=positions_value,
        daily_pnl=snapshot_daily_pnl,
        cumulative_pnl=prev_cumulative + snapshot_daily_pnl,
    )
    db.add(snapshot)

    # Update risk manager peak
    await update_portfolio_peak(db, portfolio_value)

    await db.commit()

    summary = {
        "portfolio_value": portfolio_value,
        "cash": cash,
        "positions_value": positions_value,
        "positions_synced": synced_count,
        "daily_pnl": snapshot_daily_pnl,
    }
    logger.info("Portfolio synced: %s", summary)
    return summary


async def get_portfolio_summary(db: AsyncSession) -> dict:
    """Get current portfolio summary from local DB."""
    # Positions
    result = await db.execute(
        select(PortfolioPosition, Stock.symbol)
        .join(Stock, Stock.id == PortfolioPosition.stock_id)
    )
    positions = [
        {
            "stock_id": pos.stock_id,
            "symbol": sym,
            "shares": pos.shares,
            "avg_cost_basis": pos.avg_cost_basis,
            "current_value": pos.current_value,
            "unrealized_pnl": pos.unrealized_pnl,
            "realized_pnl": pos.realized_pnl,
        }
        for pos, sym in result.all()
    ]

    # Latest snapshot
    snap_result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    snap = snap_result.scalar_one_or_none()

    # Account info from Alpaca (live data)
    account = await get_account_info()

    return {
        "total_value": account.get("portfolio_value", snap.total_value if snap else 0),
        "cash": account.get("cash", snap.cash if snap else 0),
        "positions_value": snap.positions_value if snap else 0,
        "daily_pnl": snap.daily_pnl if snap else 0,
        "cumulative_pnl": snap.cumulative_pnl if snap else 0,
        "buying_power": account.get("buying_power", 0),
        "positions": positions,
        "account_status": account.get("status", "unknown"),
    }


async def get_portfolio_history(db: AsyncSession, days: int = 90) -> list[dict]:
    """Get daily portfolio snapshots for charting."""
    result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(days * 12)  # ~12 snapshots per day at 5-min intervals
    )
    snapshots = result.scalars().all()
    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "total_value": s.total_value,
            "cash": s.cash,
            "positions_value": s.positions_value,
            "daily_pnl": s.daily_pnl,
            "cumulative_pnl": s.cumulative_pnl,
        }
        for s in reversed(snapshots)
    ]
