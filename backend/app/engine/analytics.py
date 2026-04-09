"""Performance analytics engine — calculates metrics from actual trade history.

Computes Sharpe ratio, max drawdown, win rate, profit factor, Calmar ratio,
monthly returns, and signal attribution.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import PortfolioSnapshot
from app.models.trade import Trade, ProposedTrade

logger = logging.getLogger(__name__)


async def calculate_performance(db: AsyncSession) -> dict:
    """Calculate comprehensive performance metrics from trade history."""
    # Get all filled trades
    result = await db.execute(
        select(Trade).where(Trade.status == "filled").order_by(Trade.fill_time)
    )
    trades = result.scalars().all()

    if not trades:
        return _empty_metrics()

    # Pair buy/sell trades by stock to compute P&L per round-trip
    buys: dict[int, list] = defaultdict(list)
    round_trips: list[dict] = []

    for t in trades:
        if t.action == "buy":
            buys[t.stock_id].append(t)
        elif t.action == "sell" and buys[t.stock_id]:
            buy = buys[t.stock_id].pop(0)
            buy_price = buy.fill_price or buy.price
            sell_price = t.fill_price or t.price
            pnl = (sell_price - buy_price) * t.shares
            pnl_pct = (sell_price - buy_price) / buy_price if buy_price > 0 else 0
            round_trips.append({
                "stock_id": t.stock_id,
                "buy_trade_id": buy.id,
                "sell_trade_id": t.id,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "shares": t.shares,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "proposed_trade_id": buy.proposed_trade_id,
                "sell_proposed_trade_id": t.proposed_trade_id,
            })

    # Basic metrics
    total_trades = len(round_trips)
    if total_trades == 0:
        return _empty_metrics()

    wins = [r for r in round_trips if r["pnl"] > 0]
    losses = [r for r in round_trips if r["pnl"] <= 0]
    win_rate = len(wins) / total_trades if total_trades > 0 else 0

    total_pnl = sum(r["pnl"] for r in round_trips)
    gross_profit = sum(r["pnl"] for r in wins)
    gross_loss = abs(sum(r["pnl"] for r in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    # Returns for Sharpe & drawdown
    returns = [r["pnl_pct"] for r in round_trips]
    avg_return = sum(returns) / len(returns) if returns else 0
    std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 0

    # Annualized Sharpe (assume ~252 trading days, ~1 trade/day avg)
    sharpe_ratio = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0

    # Max drawdown from portfolio snapshots
    snap_result = await db.execute(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp)
    )
    snapshots = snap_result.scalars().all()

    max_drawdown = 0.0
    peak_value = 0.0
    equity_curve = []

    for s in snapshots:
        if s.total_value > peak_value:
            peak_value = s.total_value
        if peak_value > 0:
            dd = (peak_value - s.total_value) / peak_value
            if dd > max_drawdown:
                max_drawdown = dd
        equity_curve.append({
            "timestamp": s.timestamp.isoformat(),
            "value": s.total_value,
        })

    # Calmar ratio (annualized return / max drawdown)
    total_return_pct = sum(returns) if returns else 0
    calmar_ratio = total_return_pct / max_drawdown if max_drawdown > 0 else 0

    # Monthly returns
    monthly_returns = _calculate_monthly_returns(snapshots)

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "total_pnl": round(total_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_return_pct": round(avg_return * 100, 4),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "calmar_ratio": round(calmar_ratio, 4),
        "monthly_returns": monthly_returns,
        "equity_curve": equity_curve[-500:],  # Last 500 points
    }


async def calculate_attribution(db: AsyncSession) -> dict:
    """Determine which signal source (ML, Claude, analyst) drives wins vs losses."""
    # Get all filled trades with their proposed trade IDs
    result = await db.execute(
        select(Trade).where(
            Trade.status == "filled",
            Trade.proposed_trade_id.isnot(None),
        )
    )
    filled_trades = result.scalars().all()

    # Get proposed trades for signal source info
    proposed_ids = [t.proposed_trade_id for t in filled_trades if t.proposed_trade_id]
    if not proposed_ids:
        return {"ml": _empty_source(), "claude": _empty_source(), "analyst": _empty_source()}

    result = await db.execute(
        select(ProposedTrade).where(ProposedTrade.id.in_(proposed_ids))
    )
    proposed_map = {p.id: p for p in result.scalars().all()}

    # Pair buy/sell to get P&L
    buys: dict[int, list] = defaultdict(list)
    attributed: dict[str, list[float]] = {"ml": [], "claude": [], "analyst": []}

    for t in filled_trades:
        if t.action == "buy":
            buys[t.stock_id].append(t)
        elif t.action == "sell" and buys[t.stock_id]:
            buy = buys[t.stock_id].pop(0)
            buy_price = buy.fill_price or buy.price
            sell_price = t.fill_price or t.price
            pnl = (sell_price - buy_price) * t.shares

            # Attribute to signal sources from the buy's proposed trade
            proposed = proposed_map.get(buy.proposed_trade_id)
            if proposed:
                if proposed.ml_signal_id:
                    attributed["ml"].append(pnl)
                if proposed.synthesis_id:
                    attributed["claude"].append(pnl)
                if proposed.analyst_input_id:
                    attributed["analyst"].append(pnl)

    result = {}
    for source, pnls in attributed.items():
        if not pnls:
            result[source] = _empty_source()
            continue

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        result[source] = {
            "total_trades": len(pnls),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "gross_profit": round(sum(wins), 2),
            "gross_loss": round(abs(sum(losses)), 2),
        }

    return result


def _calculate_monthly_returns(snapshots: list) -> list[dict]:
    """Calculate monthly return percentages from snapshots."""
    if not snapshots:
        return []

    monthly: dict[str, dict] = {}
    for s in snapshots:
        key = s.timestamp.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"first": s.total_value, "last": s.total_value}
        monthly[key]["last"] = s.total_value

    result = []
    prev_value = None
    for month_key in sorted(monthly.keys()):
        m = monthly[month_key]
        start_val = prev_value if prev_value else m["first"]
        end_val = m["last"]
        ret_pct = ((end_val - start_val) / start_val * 100) if start_val > 0 else 0
        result.append({
            "month": month_key,
            "return_pct": round(ret_pct, 2),
            "start_value": round(start_val, 2),
            "end_value": round(end_val, 2),
        })
        prev_value = end_val

    return result


def _empty_metrics() -> dict:
    return {
        "total_trades": 0,
        "win_rate": 0,
        "profit_factor": 0,
        "total_pnl": 0,
        "gross_profit": 0,
        "gross_loss": 0,
        "avg_return_pct": 0,
        "sharpe_ratio": 0,
        "max_drawdown_pct": 0,
        "calmar_ratio": 0,
        "monthly_returns": [],
        "equity_curve": [],
    }


def _empty_source() -> dict:
    return {
        "total_trades": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0,
        "total_pnl": 0,
        "avg_pnl": 0,
        "gross_profit": 0,
        "gross_loss": 0,
    }
