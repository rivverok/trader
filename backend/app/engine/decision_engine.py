"""Decision engine — delegates trade decisions to the RL agent.

The old Claude-based weighted-signal pipeline has been removed.
All signal data (ML, sentiment, synthesis, analyst input) is now consumed
by the RL agent via state snapshots. This module provides portfolio
context helpers used by the state snapshot service and RL inference task.
"""

import logging
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.risk_manager import get_risk_state
from app.models.portfolio import PortfolioPosition, PortfolioSnapshot
from app.models.stock import Stock
from app.models.trade import Trade

logger = logging.getLogger(__name__)


async def run_decision_cycle(db: AsyncSession) -> dict[str, Any]:
    """Decision cycle — now delegated to the RL inference task.

    This function is kept as a thin wrapper for backward compatibility.
    In trading mode the RL inference task (run_rl_inference_task) handles
    the full predict → risk check → propose pipeline.
    """
    from app.tasks.task_status import get_system_mode

    mode = get_system_mode()
    if mode != "trading":
        return {"status": "skipped", "reason": f"system in {mode} mode — use RL inference task in trading mode"}

    from app.engine.rl_agent import rl_agent

    if not rl_agent.is_loaded:
        return {"status": "skipped", "reason": "no RL model loaded"}

    return {"status": "skipped", "reason": "use run_rl_inference_task directly"}


# ── Portfolio context helpers (used by state snapshots and RL inference) ──


async def _build_portfolio_context(
    db: AsyncSession, risk_state: Any, portfolio_value: float
) -> dict[str, Any]:
    """Gather portfolio stats for state snapshots and RL inference context."""
    # Count open positions
    pos_result = await db.execute(
        select(func.count(PortfolioPosition.id)).where(PortfolioPosition.shares > 0)
    )
    open_positions = pos_result.scalar() or 0

    # Latest snapshot for cash
    snap_result = await db.execute(
        select(PortfolioSnapshot).order_by(desc(PortfolioSnapshot.timestamp)).limit(1)
    )
    snap = snap_result.scalar_one_or_none()
    cash = snap.cash if snap else portfolio_value

    # Recent trade stats (last 30 filled trades)
    trade_result = await db.execute(
        select(Trade)
        .where(Trade.status == "filled")
        .order_by(desc(Trade.fill_time))
        .limit(30)
    )
    recent_trades = trade_result.scalars().all()

    win_rate = 0.0
    total_recent_trades = 0
    if recent_trades:
        # Simple win count: buy trades where we later sold higher
        # For quick context, just count total filled trades
        total_recent_trades = len(recent_trades)

    # Drawdown from peak
    drawdown_pct = 0.0
    if portfolio_value > 0 and risk_state.portfolio_peak_value > 0:
        drawdown_pct = (
            (risk_state.portfolio_peak_value - portfolio_value)
            / risk_state.portfolio_peak_value
        ) * 100

    return {
        "portfolio_value": portfolio_value,
        "cash": cash,
        "cash_pct": (cash / portfolio_value * 100) if portfolio_value > 0 else 100,
        "open_positions": open_positions,
        "recent_trade_count": total_recent_trades,
        "daily_realized_loss": risk_state.daily_realized_loss,
        "daily_loss_limit": risk_state.daily_loss_limit,
        "drawdown_from_peak_pct": drawdown_pct,
        "max_drawdown_pct": risk_state.max_drawdown_pct,
        "portfolio_peak": risk_state.portfolio_peak_value,
    }


async def _get_watchlist(db: AsyncSession) -> list[Stock]:
    result = await db.execute(
        select(Stock).where(Stock.on_watchlist.is_(True))
    )
    return list(result.scalars().all())


async def _get_portfolio_value(db: AsyncSession, use_live: bool = False) -> float:
    """Get total portfolio value.

    When use_live=True (growth mode), query Alpaca for real-time equity
    so position sizing reflects the actual account balance including cash.
    Falls back to latest snapshot if Alpaca is unreachable.
    """
    if use_live:
        try:
            from app.engine.executor import get_account_info
            account = await get_account_info()
            equity = account.get("equity", 0)
            if equity > 0:
                return equity
        except Exception:
            pass  # fall through to snapshot

    result = await db.execute(
        select(PortfolioSnapshot).order_by(desc(PortfolioSnapshot.timestamp)).limit(1)
    )
    snap = result.scalar_one_or_none()
    return snap.total_value if snap else settings.RISK_MAX_TRADE_DOLLARS * 100
