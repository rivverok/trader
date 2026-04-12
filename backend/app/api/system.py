"""API routes for system controls — pause/resume, auto-execute, manual trades, emergency stop."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.executor import close_all_positions, execute_trade, get_account_info
from app.engine.risk_manager import get_risk_state, check_trade_allowed
from app.models.stock import Stock
from app.models.trade import ProposedTrade, Trade

router = APIRouter(prefix="/api/system", tags=["system"])


# ── Schemas ──────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    system_mode: str
    trading_paused: bool
    system_paused: bool
    trading_halted: bool
    halt_reason: str | None
    account_status: str
    buying_power: float
    portfolio_value: float


class ManualTradeRequest(BaseModel):
    symbol: str
    action: str = Field(pattern=r"^(buy|sell)$")
    shares: float = Field(gt=0)
    order_type: str = "market"
    price_target: float | None = None


class ManualTradeResponse(BaseModel):
    trade_id: int
    proposed_trade_id: int
    status: str
    risk_check_passed: bool
    risk_check_reason: str


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/status", response_model=SystemStatus)
async def system_status(db: AsyncSession = Depends(get_db)):
    """Get system status — auto-execute flag, pause state, account info."""
    state = await get_risk_state(db)
    account = await get_account_info()
    return SystemStatus(
        system_mode=state.system_mode,
        trading_paused=state.trading_paused,
        system_paused=state.system_paused,
        trading_halted=state.trading_halted,
        halt_reason=state.halt_reason,
        account_status=account.get("status", "unknown"),
        buying_power=account.get("buying_power", 0),
        portfolio_value=account.get("portfolio_value", 0),
    )


@router.post("/pause")
async def pause_trading(db: AsyncSession = Depends(get_db)):
    """Pause all trading — no new trades will execute."""
    state = await get_risk_state(db)
    state.trading_paused = True
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "paused"}


@router.post("/resume")
async def resume_trading(db: AsyncSession = Depends(get_db)):
    """Resume trading after pause."""
    state = await get_risk_state(db)
    state.trading_paused = False
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "resumed"}


@router.post("/auto-execute")
async def toggle_auto_execute(
    enable: bool,
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable auto-execution of proposed trades."""
    state = await get_risk_state(db)
    state.auto_execute = enable
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"auto_execute": enable}


@router.post("/growth-mode")
async def toggle_growth_mode(
    enable: bool,
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable growth mode.

    When enabled, the system fully manages the account:
    - Auto-approves trades that pass risk checks
    - Sizes positions as a % of actual portfolio (not tiny risk-based amounts)
    - Reinvests all gains to grow account value
    """
    state = await get_risk_state(db)
    state.growth_mode = enable
    # Growth mode implies auto-execute
    if enable:
        state.auto_execute = True
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"growth_mode": enable, "auto_execute": state.auto_execute}


@router.post("/pause-system")
async def pause_system(db: AsyncSession = Depends(get_db)):
    """Pause all scheduled tasks — stops data collection, analysis, ML, and trading.

    Use this to prevent API costs (Claude, data providers, etc.) when idle.
    """
    state = await get_risk_state(db)
    state.system_paused = True
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "system_paused"}


@router.post("/resume-system")
async def resume_system(db: AsyncSession = Depends(get_db)):
    """Resume all scheduled tasks after a system pause."""
    state = await get_risk_state(db)
    state.system_paused = False
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "system_resumed"}


@router.post("/emergency-stop")
async def emergency_stop(db: AsyncSession = Depends(get_db)):
    """EMERGENCY: Close all positions and halt trading."""
    state = await get_risk_state(db)
    state.trading_halted = True
    state.trading_paused = True
    state.halt_reason = "Emergency stop triggered by user"
    state.halted_at = datetime.now(timezone.utc)
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()

    result = await close_all_positions()
    return {"status": "emergency_stop", "positions_closed": result}


@router.post("/trades/manual", response_model=ManualTradeResponse)
async def manual_trade(
    req: ManualTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Place a manual trade — bypasses decision engine but goes through risk check."""
    # Look up stock
    result = await db.execute(
        select(Stock).where(Stock.symbol == req.symbol.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"Stock {req.symbol} not found in database")

    # Get portfolio value for risk check
    account = await get_account_info()
    portfolio_value = account.get("portfolio_value", 0)

    # Run risk check
    price = req.price_target or account.get("equity", 0) / max(req.shares, 1)
    allowed, reason = await check_trade_allowed(
        db, stock, req.action, req.shares, price, 1.0, portfolio_value,
    )

    # Create a proposed trade record for audit trail
    proposed = ProposedTrade(
        stock_id=stock.id,
        action=req.action,
        shares=req.shares,
        price_target=req.price_target,
        order_type=req.order_type,
        confidence=1.0,
        reasoning_chain="Manual trade placed by user",
        risk_check_passed=allowed,
        risk_check_reason=reason,
        status="approved" if allowed else "rejected",
    )
    db.add(proposed)
    await db.flush()

    if not allowed:
        await db.commit()
        return ManualTradeResponse(
            trade_id=0,
            proposed_trade_id=proposed.id,
            status="rejected",
            risk_check_passed=False,
            risk_check_reason=reason,
        )

    # Execute immediately
    trade = await execute_trade(db, proposed)
    if not trade:
        return ManualTradeResponse(
            trade_id=0,
            proposed_trade_id=proposed.id,
            status="execution_failed",
            risk_check_passed=True,
            risk_check_reason="Risk check passed but execution failed",
        )

    return ManualTradeResponse(
        trade_id=trade.id,
        proposed_trade_id=proposed.id,
        status="executed",
        risk_check_passed=True,
        risk_check_reason="ok",
    )


# ── Backup status ────────────────────────────────────────────────────


@router.get("/backup-status")
async def get_backup_status(db: AsyncSession = Depends(get_db)):
    """Return last backup status written by the backup cron script."""
    from app.models.system_kv import SystemKV

    keys = ["backup_last_status", "backup_last_time", "backup_last_message"]
    result = await db.execute(select(SystemKV).where(SystemKV.key.in_(keys)))
    rows = {row.key: row.value for row in result.scalars().all()}

    return {
        "status": rows.get("backup_last_status"),
        "time": rows.get("backup_last_time"),
        "message": rows.get("backup_last_message"),
    }


# ── System Mode ──────────────────────────────────────────────────────


class SystemModeRequest(BaseModel):
    mode: str = Field(pattern=r"^(data_collection|trading)$")


@router.get("/mode")
async def get_system_mode(db: AsyncSession = Depends(get_db)):
    """Get current system mode (data_collection or trading)."""
    state = await get_risk_state(db)
    return {"mode": state.system_mode}


@router.put("/mode")
async def set_system_mode(
    req: SystemModeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Switch system mode.

    Switching to 'trading' requires an active RL model.
    """
    state = await get_risk_state(db)
    old_mode = state.system_mode

    if req.mode == "trading":
        # Verify an active RL model exists
        from app.models.rl_snapshot import RLStateSnapshot  # noqa: F401
        from app.models.rl_model import RLModel
        result = await db.execute(
            select(RLModel).where(RLModel.is_active.is_(True)).limit(1)
        )
        active_model = result.scalar_one_or_none()
        if not active_model:
            raise HTTPException(
                400,
                detail="Cannot switch to trading mode — no active RL model loaded",
            )

    state.system_mode = req.mode
    state.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "mode": req.mode,
        "previous_mode": old_mode,
    }
