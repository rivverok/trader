"""Position sizing — determines how many shares to buy/sell."""

import logging
import math

from app.config import settings

logger = logging.getLogger(__name__)


def calculate_position_size(
    action: str,
    price: float,
    portfolio_value: float,
    confidence: float,
    current_shares: float = 0.0,
    growth_mode: bool = False,
) -> float:
    """Calculate number of shares for a trade.

    In growth mode, sizes trades as a % of portfolio (default 10%) scaled by
    confidence — designed for small accounts that reinvest all gains.

    In normal mode, uses fixed-fractional: risk a fixed % of portfolio per trade,
    scaled by confidence.

    Returns number of shares (always >= 0). Returns 0 if trade should be skipped.
    """
    if price <= 0 or portfolio_value <= 0:
        return 0.0

    if growth_mode or settings.GROWTH_MODE:
        shares = _growth_sizing(action, price, portfolio_value, confidence, current_shares)
    elif settings.POSITION_SIZE_METHOD == "fixed_fractional":
        shares = _fixed_fractional(action, price, portfolio_value, confidence, current_shares)
    else:
        shares = _fixed_fractional(action, price, portfolio_value, confidence, current_shares)

    return max(0.0, math.floor(shares))


def _growth_sizing(
    action: str,
    price: float,
    portfolio_value: float,
    confidence: float,
    current_shares: float,
) -> float:
    """Growth mode: allocate X% of portfolio per trade, scaled by confidence.

    For a $1000 account with 10% position size and 0.8 confidence:
      $1000 * 10% * 0.8 = $80 → shares = 80 / price

    Cap at max_trade_dollars as a hard safety limit, and also cap at
    max_position_pct of portfolio to prevent over-concentration.
    """
    position_pct = settings.GROWTH_POSITION_PCT / 100.0
    max_trade = settings.RISK_MAX_TRADE_DOLLARS

    # Scale by confidence (higher confidence → bigger position)
    dollar_amount = portfolio_value * position_pct * confidence

    # Hard cap at max_trade_dollars
    dollar_amount = min(dollar_amount, max_trade)

    # Also cap at max_position_pct of portfolio
    max_position_dollars = portfolio_value * (settings.RISK_MAX_POSITION_PCT / 100.0)
    dollar_amount = min(dollar_amount, max_position_dollars)

    shares = dollar_amount / price

    if action == "sell":
        if current_shares > 0:
            shares = min(shares, current_shares)
        else:
            shares = shares * 0.5

    return shares


def _fixed_fractional(
    action: str,
    price: float,
    portfolio_value: float,
    confidence: float,
    current_shares: float,
) -> float:
    """Fixed fractional: risk X% of portfolio, scaled by confidence.

    Base risk: POSITION_SIZE_RISK_PCT (default 2%)
    Scaled: base_risk * confidence → dollar amount → shares
    Capped at max_trade_dollars.
    """
    base_risk_pct = settings.POSITION_SIZE_RISK_PCT / 100.0
    max_trade = settings.RISK_MAX_TRADE_DOLLARS

    # Scale risk by confidence (higher confidence → bigger position)
    risk_pct = base_risk_pct * confidence
    dollar_amount = portfolio_value * risk_pct

    # Cap at max trade dollars
    dollar_amount = min(dollar_amount, max_trade)

    shares = dollar_amount / price

    if action == "sell":
        # Don't sell more than we hold
        if current_shares > 0:
            shares = min(shares, current_shares)
        else:
            # Short selling — use reduced size
            shares = shares * 0.5

    return shares
