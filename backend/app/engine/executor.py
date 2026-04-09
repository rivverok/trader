"""Alpaca trade executor — places orders via paper trading API.

Supports market, limit, stop-loss, and bracket orders.
Records fill details back to the local database.
"""

import asyncio
import logging
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, OrderClass
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    GetOrdersRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.stock import Stock
from app.models.trade import ProposedTrade, Trade

logger = logging.getLogger(__name__)


def _get_client() -> TradingClient:
    """Create an Alpaca TradingClient (paper mode)."""
    return TradingClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
        paper=settings.ALPACA_BASE_URL.startswith("https://paper"),
    )


async def execute_trade(db: AsyncSession, proposed: ProposedTrade) -> Trade | None:
    """Place an order on Alpaca for an approved proposed trade.

    Returns a Trade record on success, or None on failure.
    """
    # Look up symbol
    result = await db.execute(
        select(Stock).where(Stock.id == proposed.stock_id)
    )
    stock = result.scalar_one_or_none()
    if not stock:
        logger.error("Stock id=%d not found for proposed trade %d", proposed.stock_id, proposed.id)
        return None

    symbol = stock.symbol
    side = OrderSide.BUY if proposed.action == "buy" else OrderSide.SELL
    qty = proposed.shares

    try:
        client = _get_client()

        # Live mode: 5-second delay before execution
        if settings.TRADING_MODE == "live":
            logger.warning(
                "LIVE MODE: 5-second delay before executing %s %s %.0f %s",
                proposed.order_type, proposed.action, qty, symbol,
            )
            await asyncio.sleep(5)

        order = _place_order(client, symbol, side, qty, proposed)

        # Create local Trade record
        trade = Trade(
            stock_id=proposed.stock_id,
            proposed_trade_id=proposed.id,
            action=proposed.action,
            shares=float(order.qty or qty),
            price=proposed.price_target or 0.0,
            order_type=proposed.order_type,
            alpaca_order_id=str(order.id),
            status="pending",
        )
        db.add(trade)

        # Mark proposed trade as executed
        proposed.status = "executed"
        proposed.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(trade)
        logger.info(
            "Order placed: %s %s %.0f shares of %s (alpaca_id=%s)",
            proposed.order_type, proposed.action, qty, symbol, order.id,
        )

        # Fire alert
        try:
            from app.engine.alert_service import create_alert
            severity = "warning" if settings.TRADING_MODE == "live" else "info"
            await create_alert(
                db, "trade_executed",
                f"{proposed.action.upper()} {qty:.0f} shares of {symbol} ({proposed.order_type})",
                severity=severity,
            )
        except Exception:
            pass  # Alert failure should never block trading

        return trade

    except Exception as e:
        logger.error("Failed to execute trade %d for %s: %s", proposed.id, symbol, e)
        proposed.status = "rejected"
        proposed.risk_check_reason = f"Execution failed: {e}"
        proposed.updated_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            from app.engine.alert_service import create_alert
            await create_alert(
                db, "system_error",
                f"Trade execution failed for {symbol}: {e}",
                severity="critical",
            )
        except Exception:
            pass

        return None


def _place_order(
    client: TradingClient,
    symbol: str,
    side: OrderSide,
    qty: float,
    proposed: ProposedTrade,
):
    """Place the appropriate order type on Alpaca."""
    order_type = proposed.order_type.lower()

    if order_type == "bracket":
        # Bracket order: entry + stop-loss + take-profit
        stop_loss_pct = settings.DEFAULT_STOP_LOSS_PCT / 100
        take_profit_pct = settings.DEFAULT_TAKE_PROFIT_PCT / 100
        entry_price = proposed.price_target or 0

        if entry_price <= 0:
            # Fall back to market order without bracket
            return client.submit_order(
                MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
            )

        stop_price = round(entry_price * (1 - stop_loss_pct), 2)
        tp_price = round(entry_price * (1 + take_profit_pct), 2)
        if side == OrderSide.SELL:
            stop_price = round(entry_price * (1 + stop_loss_pct), 2)
            tp_price = round(entry_price * (1 - take_profit_pct), 2)

        return client.submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                stop_loss=StopLossRequest(stop_price=stop_price),
                take_profit=TakeProfitRequest(limit_price=tp_price),
            )
        )

    elif order_type == "limit" and proposed.price_target:
        return client.submit_order(
            LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=proposed.price_target,
            )
        )

    elif order_type == "stop" and proposed.price_target:
        stop_loss_pct = settings.DEFAULT_STOP_LOSS_PCT / 100
        stop_price = round(proposed.price_target * (1 - stop_loss_pct), 2)
        return client.submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.OTO,
                stop_loss=StopLossRequest(stop_price=stop_price),
            )
        )

    else:
        # Default: market order
        return client.submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        )


async def sync_order_status(db: AsyncSession, trade: Trade) -> Trade:
    """Check an order's status on Alpaca and update local record."""
    if not trade.alpaca_order_id:
        return trade

    try:
        client = _get_client()
        order = client.get_order_by_id(trade.alpaca_order_id)

        alpaca_status = str(order.status.value) if order.status else "unknown"

        if alpaca_status == "filled":
            trade.status = "filled"
            trade.fill_price = float(order.filled_avg_price) if order.filled_avg_price else None
            trade.fill_time = order.filled_at
            trade.shares = float(order.filled_qty) if order.filled_qty else trade.shares
            # Calculate slippage
            if trade.fill_price and trade.price and trade.price > 0:
                trade.slippage = round(
                    abs(trade.fill_price - trade.price) / trade.price * 100, 4
                )
            trade.commission = 0.0  # Alpaca is commission-free
        elif alpaca_status == "partially_filled":
            trade.status = "partial"
            trade.fill_price = float(order.filled_avg_price) if order.filled_avg_price else None
            trade.shares = float(order.filled_qty) if order.filled_qty else trade.shares
        elif alpaca_status in ("canceled", "expired", "suspended"):
            trade.status = "cancelled"
        elif alpaca_status == "rejected":
            trade.status = "rejected"

        trade.updated_at = datetime.now(timezone.utc)
        await db.commit()

    except Exception as e:
        logger.error("Failed to sync order %s: %s", trade.alpaca_order_id, e)

    return trade


async def cancel_order(trade: Trade) -> bool:
    """Cancel an open order on Alpaca."""
    if not trade.alpaca_order_id:
        return False
    try:
        client = _get_client()
        client.cancel_order_by_id(trade.alpaca_order_id)
        logger.info("Cancelled order %s", trade.alpaca_order_id)
        return True
    except Exception as e:
        logger.error("Failed to cancel order %s: %s", trade.alpaca_order_id, e)
        return False


async def get_account_info() -> dict:
    """Get account info from Alpaca (buying power, portfolio value, etc.)."""
    try:
        client = _get_client()
        account = client.get_account()
        return {
            "status": str(account.status),
            "buying_power": float(account.buying_power),
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "equity": float(account.equity),
            "last_equity": float(account.last_equity),
            "long_market_value": float(account.long_market_value),
            "short_market_value": float(account.short_market_value),
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked": account.trading_blocked,
            "account_blocked": account.account_blocked,
        }
    except Exception as e:
        logger.error("Failed to get account info: %s", e)
        return {}


async def get_alpaca_positions() -> list[dict]:
    """Get all open positions from Alpaca."""
    try:
        client = _get_client()
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "side": str(p.side),
            }
            for p in positions
        ]
    except Exception as e:
        logger.error("Failed to get positions: %s", e)
        return []


async def close_all_positions() -> dict:
    """Emergency: close all positions on Alpaca."""
    try:
        client = _get_client()
        responses = client.close_all_positions(cancel_orders=True)
        logger.critical("EMERGENCY: Closed all positions (%d orders)", len(responses))
        return {"closed": len(responses), "status": "ok"}
    except Exception as e:
        logger.error("Failed to close all positions: %s", e)
        return {"closed": 0, "status": "error", "error": str(e)}
