"""Execution engine Celery tasks — execute trades, sync portfolio, monitor stops."""

import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from app.database import async_session
from app.engine.executor import execute_trade, sync_order_status
from app.engine.portfolio_sync import sync_portfolio
from app.engine.risk_manager import get_risk_state, record_realized_loss
from app.models.trade import ProposedTrade, Trade

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    import asyncio
    from app.database import engine
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(name="execute_approved_trades")
def execute_approved_trades_task():
    """Execute all approved (but not yet executed) trades. Runs every 1 minute."""
    from app.tasks.task_status import update_task_status, is_system_paused
    if is_system_paused():
        return {"status": "system_paused"}
    result = _run_async(_execute_approved_trades())
    update_task_status("execute_approved_trades", result)
    return result


async def _execute_approved_trades():
    async with async_session() as db:
        # Check if trading is paused or halted
        state = await get_risk_state(db)
        if state.trading_paused:
            logger.info("Trading paused — skipping execution")
            return {"status": "paused", "executed": 0}
        if state.trading_halted:
            logger.info("Trading halted — skipping execution")
            return {"status": "halted", "executed": 0}

        # Get approved trades
        result = await db.execute(
            select(ProposedTrade)
            .where(ProposedTrade.status == "approved")
            .order_by(ProposedTrade.created_at)
        )
        approved = result.scalars().all()

        if not approved:
            return {"status": "ok", "executed": 0}

        executed_count = 0
        for proposed in approved:
            trade = await execute_trade(db, proposed)
            if trade:
                executed_count += 1

        logger.info("Executed %d/%d approved trades", executed_count, len(approved))
        return {"status": "ok", "executed": executed_count, "total": len(approved)}


@shared_task(name="sync_portfolio")
def sync_portfolio_task():
    """Sync portfolio from Alpaca. Runs every 5 minutes."""
    from app.tasks.task_status import update_task_status, is_system_paused
    if is_system_paused():
        return {"status": "system_paused"}
    result = _run_async(_sync_portfolio())
    update_task_status("sync_portfolio", result)
    return result


async def _sync_portfolio():
    async with async_session() as db:
        # Also sync pending/partial trade statuses
        result = await db.execute(
            select(Trade).where(Trade.status.in_(["pending", "partial"]))
        )
        pending_trades = result.scalars().all()

        for trade in pending_trades:
            updated = await sync_order_status(db, trade)
            # If a sell trade filled, record realized P&L
            if updated.status == "filled" and updated.action == "sell" and updated.fill_price:
                pnl = (updated.fill_price - updated.price) * updated.shares
                if pnl < 0:
                    await record_realized_loss(db, abs(pnl))

        # Sync positions and snapshots
        summary = await sync_portfolio(db)
        return summary


@shared_task(name="check_stop_loss_orders")
def check_stop_loss_orders_task():
    """Monitor stop-loss and take-profit order status. Runs every 1 minute."""
    from app.tasks.task_status import update_task_status, is_system_paused
    if is_system_paused():
        return {"status": "system_paused"}
    result = _run_async(_check_stop_loss_orders())
    update_task_status("check_stop_loss_orders", result)
    return result


async def _check_stop_loss_orders():
    async with async_session() as db:
        # Find all pending trades (these include bracket legs on Alpaca)
        result = await db.execute(
            select(Trade).where(Trade.status.in_(["pending", "partial"]))
        )
        pending = result.scalars().all()

        updated_count = 0
        for trade in pending:
            prev_status = trade.status
            updated = await sync_order_status(db, trade)
            if updated.status != prev_status:
                updated_count += 1
                logger.info(
                    "Order %s status changed: %s → %s",
                    trade.alpaca_order_id, prev_status, updated.status,
                )

                # Record realized loss if a sell filled at a loss
                if (
                    updated.status == "filled"
                    and updated.action == "sell"
                    and updated.fill_price
                    and updated.price > 0
                    and updated.fill_price < updated.price
                ):
                    loss = (updated.price - updated.fill_price) * updated.shares
                    await record_realized_loss(db, loss)

        return {"status": "ok", "checked": len(pending), "updated": updated_count}


@shared_task(name="auto_execute_proposals")
def auto_execute_proposals_task():
    """When auto_execute is on, auto-approve proposed trades that pass risk checks.
    Runs every 1 minute."""
    from app.tasks.task_status import update_task_status, is_system_paused
    if is_system_paused():
        return {"status": "system_paused"}
    result = _run_async(_auto_execute_proposals())
    update_task_status("auto_execute_proposals", result)
    return result


async def _auto_execute_proposals():
    async with async_session() as db:
        state = await get_risk_state(db)
        if not state.auto_execute and not state.growth_mode:
            return {"status": "auto_execute_off", "approved": 0}
        if state.trading_paused or state.trading_halted:
            return {"status": "paused_or_halted", "approved": 0}

        # Find proposed trades that passed risk check
        result = await db.execute(
            select(ProposedTrade).where(
                ProposedTrade.status == "proposed",
                ProposedTrade.risk_check_passed == True,
            )
        )
        proposals = result.scalars().all()

        approved_count = 0
        for p in proposals:
            if p.confidence >= state.min_confidence:
                p.status = "approved"
                p.updated_at = datetime.now(timezone.utc)
                approved_count += 1

        if approved_count > 0:
            await db.commit()
            logger.info("Auto-approved %d proposals", approved_count)

        return {"status": "ok", "approved": approved_count}
