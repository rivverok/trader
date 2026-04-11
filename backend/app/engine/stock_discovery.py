"""AI-driven stock discovery engine — multi-strategy screening with Claude analysis."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.models.discovery import DiscoveryLog, WatchlistHint
from app.models.economic import EconomicIndicator
from app.models.price import Price
from app.models.stock import Stock
from app.models.analysis import ContextSynthesis
from app.models.portfolio import PortfolioPosition

logger = logging.getLogger(__name__)

WATCHLIST_MIN = 5
WATCHLIST_MAX = 20
MAX_CANDIDATES_TO_ENRICH = 25  # Limit Finnhub API calls per run

# ── Discovery preferences (override via settings) ────────────────────
DISCOVERY_PRICE_MIN = getattr(settings, "DISCOVERY_PRICE_MIN", 5.0)
DISCOVERY_PRICE_MAX = getattr(settings, "DISCOVERY_PRICE_MAX", 200.0)
DISCOVERY_MCAP_MIN_M = getattr(settings, "DISCOVERY_MCAP_MIN_M", 300)     # $300M minimum
DISCOVERY_MCAP_MAX_M = getattr(settings, "DISCOVERY_MCAP_MAX_M", 500000)  # $500B max (blocks only top ~10 companies)
DISCOVERY_PREFER_SECTORS: list[str] = []  # Empty = all sectors


async def run_stock_discovery(db: AsyncSession) -> dict[str, Any]:
    """Run multi-strategy stock discovery cycle.

    Strategies:
    1. Market movers (gainers, losers, most-active) — momentum signals
    2. Earnings catalysts — stocks reporting earnings soon
    3. Peer expansion — peers of existing watchlist stocks
    4. Sector scan — sample from under-represented sectors
    Then: enrich top candidates + Claude analysis + add/remove decisions
    """
    batch_id = f"discovery_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # ── 1. Gather existing context ───────────────────────────────────
    economic_ctx = await _get_economic_context(db)
    watchlist_ctx = await _get_watchlist_context(db)
    portfolio_ctx = await _get_portfolio_context(db)
    hints = await _get_pending_hints(db)
    watchlist_count = watchlist_ctx["count"]
    watchlist_symbols = {s["symbol"] for s in watchlist_ctx["stocks"]}

    # ── 2. Multi-strategy screening ──────────────────────────────────
    all_candidates: list[dict] = []
    strategy_stats: dict[str, int] = {}

    # Strategy A: Market movers (traditional — but limited allocation)
    movers = await _screen_movers(watchlist_symbols)
    all_candidates.extend(movers)
    strategy_stats["movers"] = len(movers)

    # Strategy B: Earnings catalysts
    earnings = await _screen_earnings_catalysts(watchlist_symbols)
    all_candidates.extend(earnings)
    strategy_stats["earnings"] = len(earnings)

    # Strategy C: Peer expansion from watchlist
    if watchlist_symbols:
        peers = await _screen_peers(watchlist_symbols)
        all_candidates.extend(peers)
        strategy_stats["peers"] = len(peers)

    # Strategy D: Sector-diversified scan
    watchlist_sectors = {s.get("sector", "") for s in watchlist_ctx["stocks"]} - {""}
    sector_picks = await _screen_sector_diversified(watchlist_symbols, watchlist_sectors)
    all_candidates.extend(sector_picks)
    strategy_stats["sector_scan"] = len(sector_picks)

    # Deduplicate by symbol within each strategy bucket
    seen = set()
    strategy_buckets: dict[str, list[dict]] = {}
    for c in all_candidates:
        sym = c["symbol"]
        if sym not in seen:
            seen.add(sym)
            strat = c.get("strategy", "unknown").split("_")[0]  # Group mover_gainer + mover_loser
            strategy_buckets.setdefault(strat, []).append(c)

    # Round-robin interleave from each strategy for fair representation
    unique_candidates: list[dict] = []
    bucket_iters = {k: iter(v) for k, v in strategy_buckets.items()}
    while bucket_iters and len(unique_candidates) < MAX_CANDIDATES_TO_ENRICH * 2:
        exhausted = []
        for strat, it in bucket_iters.items():
            try:
                unique_candidates.append(next(it))
            except StopIteration:
                exhausted.append(strat)
        for s in exhausted:
            del bucket_iters[s]

    logger.info(
        "Multi-strategy screening: %s → %d unique candidates (interleaved)",
        strategy_stats, len(unique_candidates),
    )

    # ── 3. Enrich top candidates with fundamentals ───────────────────
    candidates = unique_candidates[:MAX_CANDIDATES_TO_ENRICH]
    enriched = await _enrich_candidates(candidates)
    logger.info("Enriched %d candidates with fundamental data", len(enriched))

    # ── 4. Build prompt and call Claude ──────────────────────────────
    user_message = _build_user_message(
        economic_ctx, watchlist_ctx, portfolio_ctx, hints, watchlist_count,
        strategy_stats, enriched,
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

    # ── 5. Process ADD recommendations ───────────────────────────────
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

    # ── 6. Process REMOVE recommendations ────────────────────────────
    removed = []
    held_symbols = {p["symbol"] for p in portfolio_ctx}
    for rec in result.get("remove", []):
        symbol = rec.get("symbol", "").upper().strip()
        if not symbol:
            continue
        if symbol in held_symbols:
            logger.info("Skipping removal of %s — currently held in portfolio", symbol)
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

    # ── 7. Process hint responses ────────────────────────────────────
    hint_responses = result.get("hint_responses", {})
    await _mark_hints_processed(db, hints, hint_responses)

    await db.commit()

    # ── 8. Fire alert ────────────────────────────────────────────────
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
        total_screened = sum(strategy_stats.values())
        await create_alert(
            db, "stock_discovery",
            f"Discovery complete ({total_screened} screened via {len(strategy_stats)} strategies). {summary}. Market: {assessment[:200]}",
            severity="info",
        )
    except Exception:
        pass

    logger.info(
        "Discovery complete: strategies=%s enriched=%d added=%s removed=%s batch=%s",
        strategy_stats, len(enriched),
        added, removed, batch_id,
    )
    return {
        "status": "ok",
        "batch_id": batch_id,
        "added": added,
        "removed": removed,
        "strategies": strategy_stats,
        "enriched": len(enriched),
        "market_assessment": result.get("market_assessment", ""),
        "watchlist_health": result.get("watchlist_health", ""),
    }


# ── Screening strategies ──────────────────────────────────────────────


def _is_common_stock(sym: str) -> bool:
    """Filter out warrants, rights, units, and other derivative symbols."""
    if not sym or not sym.isascii():
        return False
    upper = sym.upper()
    for suffix in ("W", "WS", "R", "RT", "U"):
        if upper.endswith(suffix) and len(upper) > len(suffix) + 1:
            return False
    if len(sym) > 5 or not sym.isalpha():
        return False
    return True


async def _screen_movers(watchlist_symbols: set[str]) -> list[dict]:
    """Strategy A: Market movers — gainers, losers, most-active from Alpaca."""
    from app.collectors.alpaca_collector import AlpacaCollector

    alpaca = AlpacaCollector()
    candidates = []
    seen = set()

    try:
        movers_data = await alpaca.fetch_movers(top=20)
        for item in movers_data.get("gainers", []):
            sym = item.get("symbol", "")
            price = item.get("price", 0) or 0
            if sym and sym not in seen and sym not in watchlist_symbols and _is_common_stock(sym) and price >= DISCOVERY_PRICE_MIN:
                seen.add(sym)
                candidates.append({
                    "symbol": sym,
                    "strategy": "mover_gainer",
                    "percent_change": item.get("percent_change", 0),
                    "price": price,
                    "volume": item.get("trade_count", 0),
                })
        for item in movers_data.get("losers", []):
            sym = item.get("symbol", "")
            price = item.get("price", 0) or 0
            if sym and sym not in seen and sym not in watchlist_symbols and _is_common_stock(sym) and price >= DISCOVERY_PRICE_MIN:
                seen.add(sym)
                candidates.append({
                    "symbol": sym,
                    "strategy": "mover_loser",
                    "percent_change": item.get("percent_change", 0),
                    "price": item.get("price", 0),
                    "volume": item.get("trade_count", 0),
                })
    except Exception as e:
        logger.warning("Movers screening failed: %s", e)

    try:
        active_data = await alpaca.fetch_most_active(top=20)
        for item in active_data:
            sym = item.get("symbol", "")
            if sym and sym not in seen and sym not in watchlist_symbols and _is_common_stock(sym):
                seen.add(sym)
                candidates.append({
                    "symbol": sym,
                    "strategy": "most_active",
                    "volume": item.get("volume", 0),
                    "trade_count": item.get("trade_count", 0),
                })
    except Exception as e:
        logger.warning("Most-active screening failed: %s", e)

    return candidates


async def _screen_earnings_catalysts(watchlist_symbols: set[str]) -> list[dict]:
    """Strategy B: Stocks with upcoming earnings — catalyst-driven discovery."""
    from app.collectors.finnhub_collector import FinnhubCollector

    finnhub = FinnhubCollector()
    candidates = []

    try:
        today = datetime.now(timezone.utc).date()
        from_date = today.isoformat()
        to_date = (today + timedelta(days=14)).isoformat()

        earnings = await finnhub.fetch_earnings_calendar(from_date, to_date)
        logger.info("Earnings calendar returned %d entries", len(earnings))

        # Filter to US common stocks with estimates (indicates analyst coverage)
        for entry in earnings:
            sym = entry.get("symbol", "")
            if not sym or sym in watchlist_symbols or not _is_common_stock(sym):
                continue
            # Prefer stocks with analyst estimates (indicates coverage/interest)
            eps_est = entry.get("epsEstimate")
            rev_est = entry.get("revenueEstimate")
            if eps_est is None and rev_est is None:
                continue  # Skip if no analyst coverage

            candidates.append({
                "symbol": sym,
                "strategy": "earnings_catalyst",
                "earnings_date": entry.get("date", ""),
                "eps_estimate": eps_est,
                "revenue_estimate": rev_est,
                "hour": entry.get("hour", ""),  # bmo=before market, amc=after close
            })

        # Shuffle and limit — earnings calendar can be huge
        random.shuffle(candidates)
        candidates = candidates[:15]

    except Exception as e:
        logger.warning("Earnings screening failed: %s", e)

    return candidates


async def _screen_peers(watchlist_symbols: set[str]) -> list[dict]:
    """Strategy C: Peers of current watchlist stocks — related opportunities."""
    from app.collectors.finnhub_collector import FinnhubCollector

    finnhub = FinnhubCollector()
    candidates = []
    seen = set(watchlist_symbols)

    # Pick up to 3 random watchlist stocks to find peers for
    source_symbols = random.sample(
        list(watchlist_symbols),
        min(3, len(watchlist_symbols)),
    )

    for source in source_symbols:
        try:
            peers = await finnhub.fetch_peers(source)
            for sym in peers:
                if sym and sym not in seen and _is_common_stock(sym):
                    seen.add(sym)
                    candidates.append({
                        "symbol": sym,
                        "strategy": "peer_expansion",
                        "peer_of": source,
                    })
        except Exception as e:
            logger.debug("Peer lookup failed for %s: %s", source, e)

    return candidates


async def _screen_sector_diversified(
    watchlist_symbols: set[str],
    watchlist_sectors: set[str],
) -> list[dict]:
    """Strategy D: Sample from a curated mid-cap universe across sectors.

    Uses a seed list of quality stocks (~200) spanning all major sectors.
    Picks randomly from sectors NOT already on the watchlist.
    """
    # Curated universe: quality mid/large-cap stocks across sectors
    # These are real, liquid, US-listed stocks with analyst coverage
    SECTOR_UNIVERSE = {
        "Technology": ["CRWD", "PANW", "FTNT", "ZS", "NET", "DDOG", "SNOW", "MDB", "HUBS", "TWLO",
                       "OKTA", "ZEN", "BILL", "PCOR", "DOCN", "CFLT", "PATH", "ESTC", "GTLB", "BRZE"],
        "Healthcare": ["VEEV", "DXCM", "ALGN", "HOLX", "PODD", "NVCR", "RARE", "SMMT", "AVTR", "AZTA",
                       "ILMN", "RGEN", "BMRN", "EXAS", "HALO", "ALNY", "SRPT", "INCY", "NBIX", "MRNA"],
        "Financials": ["COIN", "HOOD", "SOFI", "LPLA", "IBKR", "MKTX", "CBOE", "FDS", "MSCI", "NDAQ",
                       "WEX", "PYPL", "SQ", "AFRM", "UPST", "FOUR", "PAYO", "RELY", "STNE", "TOST"],
        "Industrials": ["AXON", "TDG", "BLDR", "WSC", "RBC", "GNRC", "PAYC", "TREX", "SITE", "FIX",
                        "PRIM", "AAON", "WFRD", "BWXT", "KRATOS", "RKLB", "ASTS", "LUNR", "JOBY", "ACHR"],
        "Consumer": ["DECK", "LULU", "BROS", "DPZ", "CMG", "CAVA", "SHAK", "WING", "ELF", "CELH",
                     "MNST", "YETI", "CROX", "ON", "DUOL", "DKNG", "PENN", "CHWY", "WOOF", "FRPT"],
        "Energy": ["FANG", "CTRA", "DINO", "TRGP", "AM", "AROC", "NEXT", "RUN", "ENPH", "SEDG",
                   "NOVA", "SHLS", "ORA", "STEM", "PLUG", "FCEL", "BE", "CLNE", "CHPT", "BLNK"],
        "REITs": ["INVH", "AMH", "REXR", "TRNO", "SUI", "ELS", "IIPR", "COLD", "STAG", "NNN",
                  "EPRT", "KREF", "BRSP", "GLPI", "VICI", "ARES", "OWL", "STEP", "APO", "BX"],
        "Materials": ["MP", "ALB", "LTHM", "CC", "AXTA", "RPM", "VMC", "MLM", "EXP", "ITE",
                      "WOLF", "AEHR", "ACLS", "MKSI", "ENTG", "QLYS", "CYBR", "SMAR", "TENB", "VRNS"],
        "Utilities": ["CEG", "VST", "NRG", "OGE", "PNW", "IDA", "AVA", "EVRG", "NWE", "ALE",
                      "AES", "BEP", "CWEN", "NOVA", "RNW", "AQN", "SPWR", "ARRY", "MAXN", "CSIQ"],
        "Telecom": ["TMUS", "LBRDA", "SIRI", "LUMN", "USM", "GSAT", "IRDM", "GILT", "SATS", "ASTS"],
    }

    candidates = []
    available_sectors = list(SECTOR_UNIVERSE.keys())
    random.shuffle(available_sectors)

    for sector in available_sectors:
        stocks = SECTOR_UNIVERSE[sector]
        # Filter out stocks already on watchlist
        available = [s for s in stocks if s not in watchlist_symbols]
        if not available:
            continue
        # Pick 2-3 random stocks from this sector
        picks = random.sample(available, min(3, len(available)))
        for sym in picks:
            candidates.append({
                "symbol": sym,
                "strategy": "sector_scan",
                "sector_hint": sector,
            })

    return candidates


async def _enrich_candidates(candidates: list[dict]) -> list[dict]:
    """Enrich candidate stocks with fundamental data from Finnhub.

    Applies price/market-cap filters to focus on the sweet spot.
    """
    from app.collectors.finnhub_collector import FinnhubCollector

    finnhub = FinnhubCollector()
    enriched = []

    for candidate in candidates:
        symbol = candidate["symbol"]
        data = dict(candidate)

        try:
            profile = await finnhub.fetch_company_profile(symbol)
            data["name"] = profile.get("name", "")
            data["sector"] = profile.get("sector", "")
            data["market_cap"] = profile.get("market_cap", 0)
            data["country"] = profile.get("country", "")

            # Skip if Finnhub has no profile (warrants, rights, etc.)
            if not data["name"]:
                logger.info("Enrichment skip %s: no profile", symbol)
                continue
            # Apply market cap filter (in millions)
            mcap = data.get("market_cap", 0) or 0
            if mcap and mcap < DISCOVERY_MCAP_MIN_M:
                logger.info("Enrichment skip %s: cap $%dM < $%dM", symbol, mcap, DISCOVERY_MCAP_MIN_M)
                continue
            if mcap and mcap > DISCOVERY_MCAP_MAX_M:
                logger.info("Enrichment skip %s: cap $%dM > $%dM", symbol, mcap, DISCOVERY_MCAP_MAX_M)
                continue
            logger.info("Enrichment pass %s (%s) cap $%.0fM", symbol, data["name"], mcap)
        except Exception as e:
            logger.info("Enrichment error %s: %s", symbol, e)

        try:
            financials = await finnhub.fetch_basic_financials(symbol)
            data["financials"] = financials
        except Exception as e:
            logger.debug("Failed to fetch financials for %s: %s", symbol, e)

        try:
            recs = await finnhub.fetch_recommendations(symbol)
            if recs:
                latest = recs[0]
                data["analyst_buy"] = latest.get("buy", 0) + latest.get("strongBuy", 0)
                data["analyst_hold"] = latest.get("hold", 0)
                data["analyst_sell"] = latest.get("sell", 0) + latest.get("strongSell", 0)
        except Exception as e:
            logger.debug("Failed to fetch recommendations for %s: %s", symbol, e)

        # Apply price filter only if we have a real current price (not 52-week high)
        price = data.get("price", 0)
        if price and (price < DISCOVERY_PRICE_MIN or price > DISCOVERY_PRICE_MAX):
            logger.debug("Skipping %s — price $%.2f outside range $%.0f-$%.0f", symbol, price, DISCOVERY_PRICE_MIN, DISCOVERY_PRICE_MAX)
            continue

        enriched.append(data)

    return enriched


# ── Context gatherers ────────────────────────────────────────────────


async def _get_economic_context(db: AsyncSession) -> list[dict]:
    """Get latest economic indicators from the database."""
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
    """Get current watchlist stocks with synthesis scores and performance data."""
    result = await db.execute(
        select(Stock).where(Stock.on_watchlist.is_(True)).order_by(Stock.symbol)
    )
    stocks = result.scalars().all()

    entries = []
    for stock in stocks:
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

        # When was this stock added to the watchlist?
        add_log = await db.execute(
            select(DiscoveryLog)
            .where(
                DiscoveryLog.symbol == stock.symbol,
                DiscoveryLog.action == "add",
            )
            .order_by(DiscoveryLog.created_at.desc())
            .limit(1)
        )
        add_entry = add_log.scalar_one_or_none()
        if add_entry:
            entry["added_at"] = add_entry.created_at.isoformat()
            days_on = (datetime.now(timezone.utc) - add_entry.created_at).days
            entry["days_on_watchlist"] = days_on

            # Price at the time of addition (closest daily close)
            add_price_result = await db.execute(
                select(Price.close)
                .where(
                    Price.stock_id == stock.id,
                    Price.interval == "1Day",
                    Price.timestamp <= add_entry.created_at,
                )
                .order_by(Price.timestamp.desc())
                .limit(1)
            )
            add_price = add_price_result.scalar_one_or_none()
            if add_price:
                entry["price_at_add"] = round(add_price, 2)

        # Current/latest price
        latest_price_result = await db.execute(
            select(Price.close)
            .where(Price.stock_id == stock.id, Price.interval == "1Day")
            .order_by(Price.timestamp.desc())
            .limit(1)
        )
        latest_price = latest_price_result.scalar_one_or_none()
        if latest_price:
            entry["current_price"] = round(latest_price, 2)

        # Calculate performance since addition
        if entry.get("price_at_add") and entry.get("current_price"):
            change_pct = ((entry["current_price"] - entry["price_at_add"]) / entry["price_at_add"]) * 100
            entry["change_since_added_pct"] = round(change_pct, 2)

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
    strategy_stats: dict[str, int],
    enriched_candidates: list[dict],
) -> str:
    sections = []

    # Multi-strategy screening results
    lines = ["## Screening Strategies Used"]
    total = sum(strategy_stats.values())
    lines.append(f"Total unique candidates screened: {total}")
    for strategy, count in strategy_stats.items():
        lines.append(f"- **{strategy}**: {count} candidates")
    lines.append(f"\nPreferences: price ${DISCOVERY_PRICE_MIN:.0f}–${DISCOVERY_PRICE_MAX:.0f}, "
                 f"market cap ${DISCOVERY_MCAP_MIN_M:,}M–${DISCOVERY_MCAP_MAX_M:,}M")
    sections.append("\n".join(lines))

    # Enriched candidates with fundamentals
    if enriched_candidates:
        lines = [f"## Enriched Candidate Stocks ({len(enriched_candidates)} stocks)"]
        for c in enriched_candidates:
            parts = [f"**{c['symbol']}**"]
            if c.get("name"):
                parts[0] += f" ({c['name']})"
            if c.get("strategy"):
                parts.append(f"Found via: {c['strategy']}")
            if c.get("sector"):
                parts.append(f"Sector: {c['sector']}")
            if c.get("percent_change"):
                parts.append(f"Day change: {c['percent_change']:+.2f}%")
            if c.get("market_cap"):
                parts.append(f"Market cap: ${c['market_cap']:.0f}M")
            if c.get("earnings_date"):
                parts.append(f"Earnings: {c['earnings_date']}")
            if c.get("peer_of"):
                parts.append(f"Peer of: {c['peer_of']}")

            fin = c.get("financials", {})
            if fin.get("pe_ratio"):
                parts.append(f"P/E: {fin['pe_ratio']:.1f}")
            if fin.get("beta"):
                parts.append(f"Beta: {fin['beta']:.2f}")
            if fin.get("52_week_return") is not None:
                parts.append(f"52wk return: {fin['52_week_return']:.1f}%")
            if fin.get("rsi_14d"):
                parts.append(f"RSI(14): {fin['rsi_14d']:.1f}")
            if fin.get("dividend_yield"):
                parts.append(f"Div yield: {fin['dividend_yield']:.2f}%")
            if fin.get("net_margin"):
                parts.append(f"Net margin: {fin['net_margin']:.1f}%")

            analyst_parts = []
            if c.get("analyst_buy"):
                analyst_parts.append(f"Buy: {c['analyst_buy']}")
            if c.get("analyst_hold"):
                analyst_parts.append(f"Hold: {c['analyst_hold']}")
            if c.get("analyst_sell"):
                analyst_parts.append(f"Sell: {c['analyst_sell']}")
            if analyst_parts:
                parts.append(f"Analysts: [{', '.join(analyst_parts)}]")

            lines.append("- " + " | ".join(parts))
        sections.append("\n".join(lines))
    else:
        sections.append("## Enriched Candidates\nNo candidates could be enriched with fundamental data. Market may be closed.")

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
            if s.get("days_on_watchlist") is not None:
                parts.append(f"On watchlist: {s['days_on_watchlist']} days")
            if s.get("price_at_add") is not None and s.get("current_price") is not None:
                parts.append(f"Price: ${s['price_at_add']:.2f} → ${s['current_price']:.2f}")
            elif s.get("current_price") is not None:
                parts.append(f"Current price: ${s['current_price']:.2f}")
            if s.get("change_since_added_pct") is not None:
                parts.append(f"Since added: {s['change_since_added_pct']:+.1f}%")
            if s.get("sentiment") is not None:
                parts.append(f"AI Sentiment: {s['sentiment']:.2f}")
            if s.get("confidence") is not None:
                parts.append(f"Confidence: {s['confidence']:.2f}")
            if s.get("key_factors"):
                parts.append(f"Factors: {', '.join(s['key_factors'][:2])}")
            lines.append("- " + " | ".join(parts))
    else:
        lines.append("Watchlist is empty — this is the initial discovery run. Build a diversified starting watchlist from the screened candidates.")
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
        f"- Only recommend stocks from the screened candidates above or user hints\n"
        f"- Do NOT invent or hallucinate stock symbols"
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
