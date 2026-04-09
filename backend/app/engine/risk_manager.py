"""Risk manager — HARD-CODED checks that cannot be overridden by AI.

Every proposed trade must pass all checks before being approved.
Circuit breakers halt ALL trading until the user manually resumes.
"""

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import PortfolioPosition
from app.models.risk import RiskState
from app.models.stock import Stock
from app.models.trade import Trade

logger = logging.getLogger(__name__)


async def get_risk_state(db: AsyncSession) -> RiskState:
    """Get the singleton risk state row, creating it if missing."""
    result = await db.execute(select(RiskState).where(RiskState.id == 1))
    state = result.scalar_one_or_none()
    if state is None:
        state = RiskState(id=1)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    # Reset daily loss counter if date changed
    today = date.today()
    if state.last_reset_date != today:
        state.daily_realized_loss = 0.0
        state.last_reset_date = today
        await db.commit()
    return state


async def check_trade_allowed(
    db: AsyncSession,
    stock: Stock,
    action: str,
    shares: float,
    price: float,
    confidence: float,
    portfolio_value: float,
) -> tuple[bool, str]:
    """Run all risk checks on a proposed trade.

    Returns (allowed: bool, reason: str).
    reason is 'ok' if allowed, otherwise explains the rejection.
    """
    from app.config import settings

    state = await get_risk_state(db)
    trade_dollars = shares * price

    # In live mode, apply stricter risk limits (50% of paper limits)
    live = settings.TRADING_MODE == "live"
    live_mult = 0.5 if live else 1.0

    # 1. Trading halted?
    if state.trading_halted:
        return False, f"Trading halted: {state.halt_reason}"

    # 2. Max $ per trade
    max_trade = state.max_trade_dollars * live_mult
    if trade_dollars > max_trade:
        return False, (
            f"Trade ${trade_dollars:.2f} exceeds max ${max_trade:.2f}"
            + (" (live mode)" if live else "")
        )

    # 3. Max % of portfolio per position
    if portfolio_value > 0:
        existing_value = await _get_position_value(db, stock.id)
        new_total = existing_value + trade_dollars if action == "buy" else existing_value
        position_pct = (new_total / portfolio_value) * 100
        if position_pct > state.max_position_pct:
            return False, (
                f"Position {position_pct:.1f}% exceeds max {state.max_position_pct:.1f}%"
            )

    # 4. Max % of portfolio per sector
    if stock.sector and portfolio_value > 0:
        sector_value = await _get_sector_value(db, stock.sector)
        new_sector = sector_value + trade_dollars if action == "buy" else sector_value
        sector_pct = (new_sector / portfolio_value) * 100
        if sector_pct > state.max_sector_pct:
            return False, (
                f"Sector '{stock.sector}' at {sector_pct:.1f}% exceeds max {state.max_sector_pct:.1f}%"
            )

    # 5. Daily realized loss limit (circuit breaker)
    daily_limit = state.daily_loss_limit * live_mult
    if state.daily_realized_loss >= daily_limit:
        await _halt_trading(
            db, state,
            f"Daily loss limit reached: ${state.daily_realized_loss:.2f} >= ${daily_limit:.2f}"
            + (" (live mode)" if live else ""),
        )
        return False, f"Daily loss limit ${daily_limit:.2f} reached"

    # 6. Max drawdown from peak (circuit breaker)
    if portfolio_value > 0 and state.portfolio_peak_value > 0:
        drawdown_pct = (
            (state.portfolio_peak_value - portfolio_value) / state.portfolio_peak_value
        ) * 100
        if drawdown_pct >= state.max_drawdown_pct:
            await _halt_trading(
                db, state,
                f"Max drawdown {drawdown_pct:.1f}% >= {state.max_drawdown_pct:.1f}%",
            )
            return False, f"Drawdown {drawdown_pct:.1f}% exceeds max {state.max_drawdown_pct:.1f}%"

    # 7. Minimum confidence threshold
    min_conf = state.min_confidence if not live else max(state.min_confidence, 0.75)
    if confidence < min_conf:
        return False, (
            f"Confidence {confidence:.3f} below minimum {min_conf:.3f}"
            + (" (live mode)" if live else "")
        )

    # 8. Market hours check (info only — Alpaca handles this for execution)
    now = datetime.now(timezone.utc)
    hour_et = (now.hour - 4) % 24  # rough UTC→ET
    if now.weekday() >= 5:
        return False, "Market closed (weekend)"
    if hour_et < 9 or hour_et >= 16:
        return False, "Market closed (outside 9:30-16:00 ET)"

    return True, "ok"


async def record_realized_loss(db: AsyncSession, loss_amount: float) -> None:
    """Record a realized loss and check circuit breaker."""
    state = await get_risk_state(db)
    state.daily_realized_loss += abs(loss_amount)
    await db.commit()

    if state.daily_realized_loss >= state.daily_loss_limit:
        await _halt_trading(
            db, state,
            f"Daily loss limit reached: ${state.daily_realized_loss:.2f}",
        )


async def update_portfolio_peak(db: AsyncSession, current_value: float) -> None:
    """Update portfolio peak value if current is higher."""
    state = await get_risk_state(db)
    if current_value > state.portfolio_peak_value:
        state.portfolio_peak_value = current_value
        await db.commit()


async def _halt_trading(db: AsyncSession, state: RiskState, reason: str) -> None:
    """Halt all trading — can only be resumed by user via API."""
    state.trading_halted = True
    state.halt_reason = reason
    state.halted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.critical("TRADING HALTED: %s", reason)

    # Fire critical alert
    try:
        from app.engine.alert_service import create_alert
        await create_alert(db, "circuit_breaker", reason, severity="critical")
    except Exception:
        pass


async def _get_position_value(db: AsyncSession, stock_id: int) -> float:
    """Get current position value for a stock."""
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.stock_id == stock_id)
    )
    pos = result.scalar_one_or_none()
    return pos.current_value if pos else 0.0


async def _get_sector_value(db: AsyncSession, sector: str) -> float:
    """Get total position value for all stocks in a sector."""
    result = await db.execute(
        select(func.coalesce(func.sum(PortfolioPosition.current_value), 0.0))
        .join(Stock, Stock.id == PortfolioPosition.stock_id)
        .where(Stock.sector == sector)
    )
    return float(result.scalar_one())
