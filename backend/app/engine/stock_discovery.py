"""AI-driven stock discovery engine — uses Claude to find and curate watchlist stocks."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.models.discovery import DiscoveryLog, WatchlistHint
from app.models.economic import EconomicIndicator
from app.models.stock import Stock
from app.models.analysis import ContextSynthesis
from app.models.portfolio import PortfolioPosition

logger = logging.getLogger(__name__)

WATCHLIST_MIN = 5
WATCHLIST_MAX = 20


async def run_stock_discovery(db: AsyncSession) -> dict[str, Any]:
    """Run the AI stock discovery cycle.

    Gathers market context, consults Claude, and updates the watchlist.
    Returns a summary of actions taken.
    """
    batch_id = f"discovery_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # ── 1. Gather context ────────────────────────────────────────────
    economic_ctx = await _get_economic_context(db)
    watchlist_ctx = await _get_watchlist_context(db)
    portfolio_ctx = await _get_portfolio_context(db)
    hints = await _get_pending_hints(db)
    watchlist_count = watchlist_ctx["count"]

    # ── 2. Build prompt and call Claude ─────────────────────────────
    user_message = _build_user_message(
        economic_ctx, watchlist_ctx, portfolio_ctx, hints, watchlist_count,
    )
    system_prompt = load_prompt("discovery")

    try:
        result = await call_claude(
            db, "stock_discovery", user_message,
            system_prompt=system_prompt,
            model=settings.CLAUDE_MODEL_SMART,
            max_tokens=4096,
        )
    except Exception as e:
        logger.error("Discovery Claude call failed: %s", e)
        return {"status": "error", "error": str(e)}

    # ── 3. Process ADD recommendations ──────────────────────────────
    added = []
    for rec in result.get("add", []):
        symbol = rec.get("symbol", "").upper().strip()
        if not symbol:
            continue
        success = await _add_stock(
            db, symbol, rec.get("reasoning", ""), rec.get("confidence", 0.5),
            batch_id,
        )
        if success:
            added.append(symbol)

    # ── 4. Process REMOVE recommendations ───────────────────────────
    removed = []
    held_symbols = {p["symbol"] for p in portfolio_ctx}
    for rec in result.get("remove", []):
        symbol = rec.get("symbol", "").upper().strip()
        if not symbol:
            continue
        if symbol in held_symbols:
            logger.info("Skipping removal of %s — currently held in portfolio", symbol)
            # Log it anyway so the user can see the AI's reasoning
            log = DiscoveryLog(
                batch_id=batch_id, action="keep", symbol=symbol,
                reasoning=f"AI recommended removal but stock is held in portfolio: {rec.get('reasoning', '')}",
                confidence=0.5, source="discovery",
            )
            db.add(log)
            continue
        success = await _remove_stock(
            db, symbol, rec.get("reasoning", ""), batch_id,
        )
        if success:
            removed.append(symbol)

    # ── 5. Process hint responses ───────────────────────────────────
    hint_responses = result.get("hint_responses", {})
    await _mark_hints_processed(db, hints, hint_responses)

    await db.commit()

    # ── 6. Fire alert ───────────────────────────────────────────────
    try:
        from app.engine.alert_service import create_alert
        msg_parts = []
        if added:
            msg_parts.append(f"Added: {', '.join(added)}")
        if removed:
            msg_parts.append(f"Removed: {', '.join(removed)}")
        if not msg_parts:
            msg_parts.append("No changes — watchlist is well-balanced")
        summary = "; ".join(msg_parts)
        assessment = result.get("market_assessment", "")
        await create_alert(
            db, "stock_discovery",
            f"Watchlist discovery complete. {summary}. Market: {assessment[:200]}",
            severity="info",
        )
    except Exception:
        pass

    logger.info(
        "Discovery complete: added=%s removed=%s batch=%s",
        added, removed, batch_id,
    )
    return {
        "status": "ok",
        "batch_id": batch_id,
        "added": added,
        "removed": removed,
        "market_assessment": result.get("market_assessment", ""),
        "watchlist_health": result.get("watchlist_health", ""),
    }


# ── Context gatherers ────────────────────────────────────────────────


async def _get_economic_context(db: AsyncSession) -> list[dict]:
    """Get latest economic indicators from the database."""
    # Get the most recent value for each indicator
    subq = (
        select(
            EconomicIndicator.indicator_code,
            func.max(EconomicIndicator.date).label("max_date"),
        )
        .group_by(EconomicIndicator.indicator_code)
        .subquery()
    )
    result = await db.execute(
        select(EconomicIndicator).join(
            subq,
            (EconomicIndicator.indicator_code == subq.c.indicator_code)
            & (EconomicIndicator.date == subq.c.max_date),
        )
    )
    indicators = result.scalars().all()
    return [
        {
            "code": ind.indicator_code,
            "name": ind.name,
            "value": ind.value,
            "date": ind.date.isoformat() if ind.date else "",
        }
        for ind in indicators
    ]


async def _get_watchlist_context(db: AsyncSession) -> dict:
    """Get current watchlist stocks with their latest synthesis scores."""
    result = await db.execute(
        select(Stock).where(Stock.on_watchlist.is_(True)).order_by(Stock.symbol)
    )
    stocks = result.scalars().all()

    entries = []
    for stock in stocks:
        # Get latest synthesis for this stock
        synth_result = await db.execute(
            select(ContextSynthesis)
            .where(ContextSynthesis.stock_id == stock.id)
            .order_by(ContextSynthesis.created_at.desc())
            .limit(1)
        )
        synth = synth_result.scalar_one_or_none()

        entry = {
            "symbol": stock.symbol,
            "name": stock.name or "",
            "sector": stock.sector or "",
            "industry": stock.industry or "",
        }
        if synth:
            entry["sentiment"] = synth.overall_sentiment
            entry["confidence"] = synth.confidence
            entry["key_factors"] = synth.key_factors
        entries.append(entry)

    return {"count": len(stocks), "stocks": entries}


async def _get_portfolio_context(db: AsyncSession) -> list[dict]:
    """Get current portfolio positions."""
    result = await db.execute(select(PortfolioPosition))
    positions = result.scalars().all()
    return [
        {
            "symbol": pos.symbol,
            "shares": pos.shares,
            "avg_cost_basis": pos.avg_cost_basis,
            "current_value": pos.current_value,
            "unrealized_pnl": pos.unrealized_pnl,
        }
        for pos in positions
    ]


async def _get_pending_hints(db: AsyncSession) -> list[dict]:
    """Get unprocessed user hints."""
    result = await db.execute(
        select(WatchlistHint)
        .where(WatchlistHint.status == "pending")
        .order_by(WatchlistHint.created_at)
    )
    hints = result.scalars().all()
    return [
        {"id": h.id, "text": h.hint_text, "symbol": h.symbol}
        for h in hints
    ]


# ── Prompt builder ───────────────────────────────────────────────────


def _build_user_message(
    economic: list[dict],
    watchlist: dict,
    portfolio: list[dict],
    hints: list[dict],
    watchlist_count: int,
) -> str:
    sections = []

    # Economic indicators
    if economic:
        lines = ["## Current Economic Indicators"]
        for ind in economic:
            lines.append(f"- **{ind['name']}** ({ind['code']}): {ind['value']} (as of {ind['date']})")
        sections.append("\n".join(lines))
    else:
        sections.append("## Economic Indicators\nNo economic data available yet.")

    # Current watchlist
    lines = [f"## Current Watchlist ({watchlist_count} stocks)"]
    if watchlist["stocks"]:
        for s in watchlist["stocks"]:
            parts = [f"**{s['symbol']}** — {s['name']}"]
            if s.get("sector"):
                parts.append(f"Sector: {s['sector']}")
            if s.get("sentiment") is not None:
                parts.append(f"AI Sentiment: {s['sentiment']:.2f}")
            if s.get("confidence") is not None:
                parts.append(f"Confidence: {s['confidence']:.2f}")
            if s.get("key_factors"):
                parts.append(f"Factors: {', '.join(s['key_factors'][:2])}")
            lines.append("- " + " | ".join(parts))
    else:
        lines.append("Watchlist is empty — this is the initial discovery run. Recommend a well-diversified starting watchlist.")
    sections.append("\n".join(lines))

    # Portfolio positions
    lines = ["## Current Portfolio Positions"]
    if portfolio:
        for p in portfolio:
            pnl_str = f"+${p['unrealized_pnl']:.2f}" if p['unrealized_pnl'] >= 0 else f"-${abs(p['unrealized_pnl']):.2f}"
            lines.append(
                f"- **{p['symbol']}**: {p['shares']} shares @ ${p['avg_cost_basis']:.2f} "
                f"(value: ${p['current_value']:.2f}, PnL: {pnl_str})"
            )
    else:
        lines.append("No open positions.")
    sections.append("\n".join(lines))

    # User hints
    if hints:
        lines = ["## User Hints (please consider these)"]
        for h in hints:
            hint_str = f"[Hint #{h['id']}]"
            if h["symbol"]:
                hint_str += f" Consider {h['symbol']}:"
            hint_str += f" {h['text']}"
            lines.append(f"- {hint_str}")
        sections.append("\n".join(lines))

    # Constraints
    sections.append(
        f"## Constraints\n"
        f"- Target watchlist size: {WATCHLIST_MIN}–{WATCHLIST_MAX} stocks\n"
        f"- Current watchlist: {watchlist_count} stocks\n"
        f"- Max additions per run: 5\n"
        f"- Only recommend actively-traded US equities on major exchanges"
    )

    return "\n\n".join(sections)


# ── Stock add/remove helpers ─────────────────────────────────────────


async def _add_stock(
    db: AsyncSession, symbol: str, reasoning: str, confidence: float, batch_id: str,
) -> bool:
    """Add a stock to the watchlist. Returns True if successful."""
    # Check if already exists
    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    existing = result.scalar_one_or_none()

    if existing and existing.on_watchlist:
        logger.info("Stock %s already on watchlist, skipping", symbol)
        return False

    if existing:
        # Re-activate
        existing.on_watchlist = True
        logger.info("Re-activated %s on watchlist", symbol)
    else:
        # Fetch metadata and create
        info = await _fetch_stock_metadata(symbol)
        if info is None:
            logger.warning("Could not validate %s on Alpaca — skipping", symbol)
            return False
        stock = Stock(
            symbol=symbol,
            name=info.get("name", ""),
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            exchange=info.get("exchange", ""),
            on_watchlist=True,
        )
        db.add(stock)

    # Log the discovery action
    log = DiscoveryLog(
        batch_id=batch_id, action="add", symbol=symbol,
        reasoning=reasoning, confidence=confidence, source="discovery",
    )
    db.add(log)
    return True


async def _remove_stock(
    db: AsyncSession, symbol: str, reasoning: str, batch_id: str,
) -> bool:
    """Remove a stock from the watchlist. Returns True if successful."""
    result = await db.execute(
        select(Stock).where(Stock.symbol == symbol, Stock.on_watchlist.is_(True))
    )
    stock = result.scalar_one_or_none()
    if not stock:
        logger.info("Stock %s not on watchlist, skipping removal", symbol)
        return False

    stock.on_watchlist = False

    log = DiscoveryLog(
        batch_id=batch_id, action="remove", symbol=symbol,
        reasoning=reasoning, confidence=0.5, source="discovery",
    )
    db.add(log)
    return True


async def _fetch_stock_metadata(symbol: str) -> dict[str, Any] | None:
    """Validate a symbol exists on Alpaca and fetch metadata."""
    try:
        from app.collectors.alpaca_collector import AlpacaCollector
        info = await AlpacaCollector().fetch_stock_info(symbol)
    except Exception:
        return None

    # Enrich with Finnhub
    try:
        from app.collectors.finnhub_collector import FinnhubCollector
        profile = await FinnhubCollector().fetch_company_profile(symbol)
        if profile.get("name"):
            info["name"] = info["name"] or profile["name"]
        if profile.get("sector"):
            info["sector"] = profile["sector"]
    except Exception:
        pass

    return info


async def _mark_hints_processed(
    db: AsyncSession, hints: list[dict], responses: dict[str, str],
) -> None:
    """Mark hints as considered and attach AI responses."""
    if not hints:
        return
    hint_ids = [h["id"] for h in hints]
    result = await db.execute(
        select(WatchlistHint).where(WatchlistHint.id.in_(hint_ids))
    )
    for hint in result.scalars().all():
        hint.status = "considered"
        hint.ai_response = responses.get(str(hint.id), "Considered during discovery cycle.")
