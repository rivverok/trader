"""Decision engine — aggregates all signals and proposes trades."""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.engine.position_sizer import calculate_position_size
from app.engine.risk_manager import check_trade_allowed, get_risk_state
from app.models.analysis import ContextSynthesis
from app.models.analyst_input import AnalystInput
from app.models.portfolio import PortfolioPosition, PortfolioSnapshot
from app.models.price import Price
from app.models.signal import MLSignal
from app.models.stock import Stock
from app.models.trade import ProposedTrade, Trade

logger = logging.getLogger(__name__)

DECISION_PROMPT = load_prompt("decision")


@dataclass
class SignalPackage:
    """Aggregated signal data for one stock."""

    stock: Stock
    ml_signal: MLSignal | None
    synthesis: ContextSynthesis | None
    analyst_input: AnalystInput | None
    current_price: float | None
    current_position: PortfolioPosition | None
    combined_score: float  # -1.0 to 1.0
    combined_confidence: float  # 0.0 to 1.0


async def run_decision_cycle(db: AsyncSession) -> dict[str, Any]:
    """Full decision cycle: aggregate → Claude review → size → risk check → propose.

    Returns summary dict with counts.
    """
    stocks = await _get_watchlist(db)
    if not stocks:
        return {"status": "skip", "reason": "no watchlist stocks"}

    risk_state = await get_risk_state(db)
    if risk_state.trading_halted:
        logger.warning("Trading halted: %s", risk_state.halt_reason)
        return {"status": "halted", "reason": risk_state.halt_reason}

    # Get portfolio value for position sizing
    # In growth mode, prefer live Alpaca equity for accurate sizing
    growth_mode = risk_state.growth_mode
    portfolio_value = await _get_portfolio_value(db, use_live=growth_mode)

    # Build portfolio context so Claude can dynamically adjust aggression
    portfolio_ctx = await _build_portfolio_context(db, risk_state, portfolio_value)

    proposed = 0
    skipped = 0
    blocked = 0
    errors = 0
    details: list[dict[str, Any]] = []

    for stock in stocks:
        try:
            pkg = await _aggregate_signals(db, stock)
            if pkg is None:
                skipped += 1
                details.append({"symbol": stock.symbol, "outcome": "skipped", "reason": "no signals (no ML signal, no synthesis, no analyst input)"})
                continue

            # Let Claude see ALL stocks with signals — it decides
            # whether to act. No static score threshold.

            # Claude decision synthesis (with portfolio context)
            decision = await _claude_decision(db, pkg, portfolio_ctx)
            if decision is None:
                skipped += 1
                details.append({"symbol": stock.symbol, "outcome": "skipped", "reason": "Claude decision failed"})
                continue

            action = _map_recommendation_to_action(decision.get("recommendation", "hold"), pkg)
            if action is None:
                skipped += 1
                details.append({"symbol": stock.symbol, "outcome": "skipped", "reason": f"Claude recommended hold (rec={decision.get('recommendation', 'hold')})"})
                continue

            # Position sizing
            price = pkg.current_price or 0.0
            if price <= 0:
                skipped += 1
                details.append({"symbol": stock.symbol, "outcome": "skipped", "reason": "no price data"})
                continue

            shares = calculate_position_size(
                action=action,
                price=price,
                portfolio_value=portfolio_value,
                confidence=decision.get("confidence", pkg.combined_confidence),
                current_shares=pkg.current_position.shares if pkg.current_position else 0,
                growth_mode=growth_mode,
            )
            if shares <= 0:
                skipped += 1
                details.append({"symbol": stock.symbol, "outcome": "skipped", "reason": f"position size 0 shares ({action} @ ${price:.2f}, confidence={decision.get('confidence', pkg.combined_confidence):.3f})"})
                continue

            # Risk check
            allowed, reason = await check_trade_allowed(
                db=db,
                stock=stock,
                action=action,
                shares=shares,
                price=price,
                confidence=decision.get("confidence", pkg.combined_confidence),
                portfolio_value=portfolio_value,
            )

            # Create proposal
            trade = ProposedTrade(
                stock_id=stock.id,
                action=action,
                shares=shares,
                price_target=decision.get("price_target"),
                order_type=decision.get("order_type", "market"),
                ml_signal_id=pkg.ml_signal.id if pkg.ml_signal else None,
                synthesis_id=pkg.synthesis.id if pkg.synthesis else None,
                analyst_input_id=pkg.analyst_input.id if pkg.analyst_input else None,
                confidence=decision.get("confidence", pkg.combined_confidence),
                reasoning_chain=decision.get("reasoning", ""),
                risk_check_passed=allowed,
                risk_check_reason=reason,
                status="proposed" if allowed else "rejected",
            )
            db.add(trade)
            if allowed:
                proposed += 1
                details.append({"symbol": stock.symbol, "outcome": "proposed", "action": action, "shares": shares, "price": price, "confidence": decision.get("confidence", pkg.combined_confidence)})
            else:
                blocked += 1
                details.append({"symbol": stock.symbol, "outcome": "blocked", "action": action, "reason": reason})
                logger.info("%s: blocked — %s", stock.symbol, reason)

        except Exception as e:
            logger.error("Decision cycle error for %s: %s", stock.symbol, e)
            errors += 1
            details.append({"symbol": stock.symbol, "outcome": "error", "reason": str(e)})

    await db.commit()
    return {
        "status": "ok",
        "proposed": proposed,
        "skipped": skipped,
        "blocked": blocked,
        "errors": errors,
        "details": details,
    }


# ── Internal helpers ──────────────────────────────────────────────────


async def _build_portfolio_context(
    db: AsyncSession, risk_state: Any, portfolio_value: float
) -> dict[str, Any]:
    """Gather portfolio stats so Claude can dynamically adjust aggression."""
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


async def _aggregate_signals(db: AsyncSession, stock: Stock) -> SignalPackage | None:
    """Gather ML signal, Claude synthesis, analyst input, price, and position."""
    # Latest ML signal
    result = await db.execute(
        select(MLSignal)
        .where(MLSignal.stock_id == stock.id)
        .order_by(desc(MLSignal.created_at))
        .limit(1)
    )
    ml_signal = result.scalar_one_or_none()

    # Latest context synthesis
    result = await db.execute(
        select(ContextSynthesis)
        .where(ContextSynthesis.stock_id == stock.id)
        .order_by(desc(ContextSynthesis.created_at))
        .limit(1)
    )
    synthesis = result.scalar_one_or_none()

    # Active analyst input
    result = await db.execute(
        select(AnalystInput)
        .where(AnalystInput.stock_id == stock.id, AnalystInput.is_active.is_(True))
        .order_by(desc(AnalystInput.updated_at))
        .limit(1)
    )
    analyst_input = result.scalar_one_or_none()

    # Need at least one signal source
    if not ml_signal and not synthesis and not analyst_input:
        logger.info("%s: no signals available, skipping", stock.symbol)
        return None

    # Current price (latest close)
    result = await db.execute(
        select(Price)
        .where(Price.stock_id == stock.id)
        .order_by(desc(Price.timestamp))
        .limit(1)
    )
    price_row = result.scalar_one_or_none()
    current_price = price_row.close if price_row else None

    # Current position
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.stock_id == stock.id)
    )
    position = result.scalar_one_or_none()

    # Combine weighted score
    score, confidence = _compute_weighted_score(ml_signal, synthesis, analyst_input)

    return SignalPackage(
        stock=stock,
        ml_signal=ml_signal,
        synthesis=synthesis,
        analyst_input=analyst_input,
        current_price=current_price,
        current_position=position,
        combined_score=score,
        combined_confidence=confidence,
    )


def _compute_weighted_score(
    ml_signal: MLSignal | None,
    synthesis: ContextSynthesis | None,
    analyst_input: AnalystInput | None,
) -> tuple[float, float]:
    """Compute weighted combined score and confidence.

    Returns (score: -1 to 1, confidence: 0 to 1).
    """
    w_ml = settings.SIGNAL_WEIGHT_ML
    w_claude = settings.SIGNAL_WEIGHT_CLAUDE
    w_analyst = settings.SIGNAL_WEIGHT_ANALYST

    total_weight = 0.0
    score = 0.0
    conf_parts: list[float] = []

    if ml_signal:
        ml_score = {"buy": 1.0, "sell": -1.0, "hold": 0.0}.get(ml_signal.signal, 0.0)
        if ml_score != 0.0:
            # Only count ML weight when it has a directional opinion.
            # "hold" means no opinion — don't let it dilute other signals.
            score += w_ml * ml_score * ml_signal.confidence
            total_weight += w_ml
        conf_parts.append(ml_signal.confidence)

    if synthesis:
        score += w_claude * synthesis.overall_sentiment
        total_weight += w_claude
        conf_parts.append(synthesis.confidence)

    if analyst_input:
        # Convert conviction (1-10) to -1..1 score via override_flag
        conv_normalized = analyst_input.conviction / 10.0
        if analyst_input.override_flag == "avoid":
            analyst_score = -conv_normalized
        elif analyst_input.override_flag == "boost":
            analyst_score = conv_normalized
        else:
            # "none" — use conviction as a magnitude indicator, direction from thesis
            analyst_score = conv_normalized * 0.5  # mild bullish lean from conviction
        score += w_analyst * analyst_score
        total_weight += w_analyst
        conf_parts.append(conv_normalized)

    if total_weight > 0:
        score /= total_weight
    confidence = sum(conf_parts) / len(conf_parts) if conf_parts else 0.0

    # Override: analyst "avoid" forces negative
    if analyst_input and analyst_input.override_flag == "avoid":
        score = min(score, -0.3)

    return max(-1.0, min(1.0, score)), max(0.0, min(1.0, confidence))


async def _claude_decision(
    db: AsyncSession, pkg: SignalPackage, portfolio_ctx: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Ask Claude for final decision synthesis on the signal package."""
    sections = [
        f"Stock: {pkg.stock.symbol} ({pkg.stock.name or 'Unknown'})",
        f"Sector: {pkg.stock.sector or 'Unknown'}",
        f"Current Price: ${pkg.current_price:.2f}" if pkg.current_price else "Current Price: unknown",
        f"Combined Score: {pkg.combined_score:+.3f} (scale: -1 sell to +1 buy)",
        f"Combined Confidence: {pkg.combined_confidence:.3f}",
    ]

    # Portfolio context — lets Claude dynamically adjust aggression
    if portfolio_ctx:
        ctx = portfolio_ctx
        sections.append(
            f"\n## Portfolio Context\n"
            f"Portfolio Value: ${ctx['portfolio_value']:,.2f} | "
            f"Cash: ${ctx['cash']:,.2f} ({ctx['cash_pct']:.1f}%)\n"
            f"Open Positions: {ctx['open_positions']} | "
            f"Recent Trades (30d): {ctx['recent_trade_count']}\n"
            f"Drawdown from Peak: {ctx['drawdown_from_peak_pct']:.1f}% "
            f"(halt at {ctx['max_drawdown_pct']:.1f}%)\n"
            f"Daily Realized Loss: ${ctx['daily_realized_loss']:.2f} "
            f"(limit: ${ctx['daily_loss_limit']:.2f})"
        )

    if pkg.current_position and pkg.current_position.shares > 0:
        pos = pkg.current_position
        sections.append(
            f"\nCurrent Position: {pos.shares:.2f} shares, "
            f"avg cost ${pos.avg_cost_basis:.2f}, "
            f"unrealized P&L ${pos.unrealized_pnl:.2f}"
        )

    if pkg.ml_signal:
        s = pkg.ml_signal
        sections.append(
            f"\n## ML Technical Signal\n"
            f"Signal: {s.signal.upper()} | Confidence: {s.confidence:.3f} | "
            f"Model: {s.model_name} v{s.model_version}"
        )

    if pkg.synthesis:
        syn = pkg.synthesis
        sections.append(
            f"\n## Claude Analysis Synthesis\n"
            f"Sentiment: {syn.overall_sentiment:+.3f} | Confidence: {syn.confidence:.3f}\n"
            f"Key Factors: {', '.join(syn.key_factors) if syn.key_factors else 'N/A'}\n"
            f"Risks: {', '.join(syn.risks) if syn.risks else 'N/A'}\n"
            f"Opportunities: {', '.join(syn.opportunities) if syn.opportunities else 'N/A'}\n"
            f"Reasoning: {syn.reasoning_chain or 'N/A'}"
        )

    if pkg.analyst_input:
        a = pkg.analyst_input
        sections.append(
            f"\n## Personal Analyst Input\n"
            f"Thesis: {a.thesis}\n"
            f"Conviction: {a.conviction}/10 | Override: {a.override_flag}\n"
            f"Catalysts: {a.catalysts or 'None specified'}\n"
            f"Time Horizon: {a.time_horizon_days or 'unspecified'} days"
        )

    user_message = "\n".join(sections)

    try:
        data = await call_claude(
            db_session=db,
            task_type="decision",
            user_message=user_message,
            system_prompt=DECISION_PROMPT,
            model=settings.CLAUDE_MODEL_SMART,
            max_tokens=2048,
        )
        return data
    except Exception as e:
        logger.error("Claude decision failed for %s: %s", pkg.stock.symbol, e)
        return None


def _map_recommendation_to_action(
    recommendation: str, pkg: SignalPackage
) -> str | None:
    """Map Claude's recommendation to buy/sell or None (hold)."""
    rec = recommendation.lower().strip()
    if rec in ("strong_buy", "buy"):
        return "buy"
    if rec in ("strong_sell", "sell"):
        # Only sell if we have a position or can short
        if pkg.current_position and pkg.current_position.shares > 0:
            return "sell"
        return "sell"  # Allow short proposals (risk manager will filter)
    return None  # hold — no trade
