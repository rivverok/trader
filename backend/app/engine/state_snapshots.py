"""State snapshot service — captures the full world state for RL training data.

Assembles per-stock features (price, technicals, signals, sentiment, synthesis,
analyst input) and global features (portfolio, market/economic) into the
rl_state_snapshots + rl_stock_snapshots tables.

Runs daily at market close and can be triggered manually.
"""

import logging
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.feature_engineering import compute_features
from app.models.analysis import ContextSynthesis, NewsAnalysis
from app.models.analyst_input import AnalystInput
from app.models.economic import EconomicIndicator
from app.models.news import NewsArticle
from app.models.portfolio import PortfolioPosition, PortfolioSnapshot
from app.models.price import Price
from app.models.rl_snapshot import RLStateSnapshot, RLStockSnapshot
from app.models.signal import MLSignal
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# Minimum price rows needed to compute meaningful technical indicators
MIN_PRICE_ROWS = 50


async def capture_snapshot(
    db: AsyncSession,
    snapshot_type: str = "daily_close",
    metadata: dict | None = None,
) -> RLStateSnapshot | None:
    """Capture a full state snapshot from all data sources.

    Returns the created RLStateSnapshot, or None if critical data is missing.
    """
    now = datetime.now(timezone.utc)

    # ── Get watchlist stocks ─────────────────────────────────────────
    result = await db.execute(
        select(Stock).where(Stock.on_watchlist.is_(True))
    )
    stocks = result.scalars().all()
    if not stocks:
        logger.warning("No watchlist stocks — skipping snapshot")
        return None

    stock_map = {s.id: s for s in stocks}
    symbols = {s.id: s.symbol for s in stocks}

    # ── Portfolio state ──────────────────────────────────────────────
    portfolio_state = await _build_portfolio_state(db, stock_map)

    # ── Market state ─────────────────────────────────────────────────
    market_state = await _build_market_state(db, now)

    # ── Create master snapshot row ───────────────────────────────────
    snapshot = RLStateSnapshot(
        timestamp=now,
        snapshot_type=snapshot_type,
        portfolio_state=portfolio_state,
        market_state=market_state,
        metadata_=metadata,
    )
    db.add(snapshot)
    await db.flush()  # get snapshot.id

    # ── Per-stock snapshots ──────────────────────────────────────────
    stock_snapshot_count = 0
    for stock_id, stock in stock_map.items():
        stock_snap = await _build_stock_snapshot(
            db, snapshot.id, stock, now
        )
        if stock_snap:
            db.add(stock_snap)
            stock_snapshot_count += 1

    await db.commit()
    logger.info(
        "Captured %s snapshot: %d stocks, snapshot_id=%d",
        snapshot_type, stock_snapshot_count, snapshot.id,
    )
    return snapshot


# ─────────────────────────────────────────────────────────────────────
#  Portfolio state
# ─────────────────────────────────────────────────────────────────────

async def _build_portfolio_state(
    db: AsyncSession,
    stock_map: dict[int, Stock],
) -> dict:
    """Assemble portfolio-level features."""
    # Current positions
    result = await db.execute(select(PortfolioPosition))
    positions = result.scalars().all()

    # Latest portfolio snapshot
    result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    latest_snap = result.scalar_one_or_none()

    total_value = latest_snap.total_value if latest_snap else 0.0
    cash = latest_snap.cash if latest_snap else 0.0
    positions_value = latest_snap.positions_value if latest_snap else 0.0
    daily_pnl = latest_snap.daily_pnl if latest_snap else 0.0
    cumulative_pnl = latest_snap.cumulative_pnl if latest_snap else 0.0

    # Position details
    position_data = []
    sector_weights: dict[str, float] = {}
    largest_pct = 0.0

    for pos in positions:
        stock = stock_map.get(pos.stock_id)
        symbol = stock.symbol if stock else f"id:{pos.stock_id}"
        sector = stock.sector if stock else "Unknown"
        weight = (pos.current_value / total_value * 100) if total_value > 0 else 0.0
        largest_pct = max(largest_pct, weight)

        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

        position_data.append({
            "symbol": symbol,
            "shares": pos.shares,
            "avg_cost_basis": pos.avg_cost_basis,
            "current_value": pos.current_value,
            "unrealized_pnl": pos.unrealized_pnl,
            "weight_pct": round(weight, 4),
        })

    # Sort sector weights descending, take top 6
    sorted_sectors = sorted(sector_weights.items(), key=lambda x: -x[1])
    top_sectors = {k: round(v, 4) for k, v in sorted_sectors[:6]}

    return {
        "total_value": total_value,
        "cash": cash,
        "positions_value": positions_value,
        "cash_pct": round(cash / total_value, 4) if total_value > 0 else 1.0,
        "num_positions": len(positions),
        "total_exposure_pct": round(
            positions_value / total_value * 100, 4
        ) if total_value > 0 else 0.0,
        "largest_position_pct": round(largest_pct, 4),
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": round(
            daily_pnl / total_value * 100, 4
        ) if total_value > 0 else 0.0,
        "cumulative_pnl": cumulative_pnl,
        "unrealized_pnl_total": sum(p.unrealized_pnl for p in positions),
        "sector_weights": top_sectors,
        "positions": position_data,
    }


# ─────────────────────────────────────────────────────────────────────
#  Market state
# ─────────────────────────────────────────────────────────────────────

async def _build_market_state(db: AsyncSession, now: datetime) -> dict:
    """Assemble market-level features (SPY, VIX proxies, economic data, calendar)."""
    market: dict = {}

    # ── SPY data (if tracked) ────────────────────────────────────────
    spy_result = await db.execute(
        select(Stock).where(Stock.symbol == "SPY")
    )
    spy_stock = spy_result.scalar_one_or_none()

    if spy_stock:
        spy_prices = await _get_price_df(db, spy_stock.id, days=250)
        if spy_prices is not None and len(spy_prices) >= 50:
            feats = compute_features(spy_prices)
            last = feats.iloc[-1]
            close = last["close"]
            sma50 = last.get("sma_50", None)
            sma200 = last.get("sma_200", None)
            market["spy_close"] = close
            market["spy_vs_sma50"] = (
                round((close / sma50) - 1, 6) if sma50 and not pd.isna(sma50) else None
            )
            market["spy_vs_sma200"] = (
                round((close / sma200) - 1, 6) if sma200 and not pd.isna(sma200) else None
            )
            market["spy_return_5d"] = _safe_round(last.get("return_5d"))
            market["spy_return_20d"] = _safe_round(last.get("return_20d"))

    # ── Latest economic indicators ───────────────────────────────────
    eco_codes = [
        "FEDFUNDS", "GS10", "GS2", "CPIAUCSL", "UNRATE", "VIXCLS",
    ]
    for code in eco_codes:
        result = await db.execute(
            select(EconomicIndicator)
            .where(EconomicIndicator.indicator_code == code)
            .order_by(EconomicIndicator.date.desc())
            .limit(1)
        )
        indicator = result.scalar_one_or_none()
        if indicator:
            market[code.lower()] = indicator.value

    # Derived: yield curve slope
    gs10 = market.get("gs10")
    gs2 = market.get("gs2")
    if gs10 is not None and gs2 is not None:
        market["yield_curve_slope"] = round(gs10 - gs2, 4)

    # VIX normalized
    vix = market.get("vixcls")
    if vix is not None:
        market["vix_normalized"] = round(vix / 30.0, 4)

    # ── Calendar features ────────────────────────────────────────────
    market["day_of_week"] = now.weekday()  # 0=Mon, 4=Fri
    market["month"] = now.month
    market["month_sin"] = round(math.sin(2 * math.pi * now.month / 12), 6)
    market["month_cos"] = round(math.cos(2 * math.pi * now.month / 12), 6)

    return market


# ─────────────────────────────────────────────────────────────────────
#  Per-stock snapshot
# ─────────────────────────────────────────────────────────────────────

async def _build_stock_snapshot(
    db: AsyncSession,
    snapshot_id: int,
    stock: Stock,
    now: datetime,
) -> RLStockSnapshot | None:
    """Assemble all features for a single stock."""
    symbol = stock.symbol
    stock_id = stock.id

    # ── Price data + technicals ──────────────────────────────────────
    price_df = await _get_price_df(db, stock_id, days=250)
    if price_df is None or len(price_df) < MIN_PRICE_ROWS:
        logger.debug("Skipping %s — only %d price rows", symbol,
                      len(price_df) if price_df is not None else 0)
        return None

    feats = compute_features(price_df)
    if feats.empty:
        return None

    last = feats.iloc[-1]
    close = last["close"]

    price_data = {
        "open": last["open"],
        "high": last["high"],
        "low": last["low"],
        "close": close,
        "volume": int(last["volume"]),
        "return_1d": _safe_round(last.get("return_1d")),
        "return_5d": _safe_round(last.get("return_5d")),
        "return_10d": _safe_round(last.get("return_10d")),
        "return_20d": _safe_round(last.get("return_20d")),
    }

    # All computed indicators as a dict (drop OHLCV to avoid duplication)
    ohlcv_cols = {"open", "high", "low", "close", "volume", "timestamp"}
    tech_dict = {}
    for col in feats.columns:
        if col not in ohlcv_cols:
            val = last[col]
            if isinstance(val, (np.floating, float)):
                if not np.isnan(val):
                    tech_dict[col] = round(float(val), 6)
            elif isinstance(val, (np.integer, int)):
                tech_dict[col] = int(val)

    # ── Latest ML signal ─────────────────────────────────────────────
    ml_signal_data = await _get_latest_ml_signal(db, stock_id)

    # ── Latest sentiment ─────────────────────────────────────────────
    sentiment_data = await _get_latest_sentiment(db, stock_id)

    # ── Latest synthesis ─────────────────────────────────────────────
    synthesis_data = await _get_latest_synthesis(db, stock_id)

    # ── Analyst input ────────────────────────────────────────────────
    analyst_data = await _get_analyst_input(db, stock_id)

    # ── Relative strength vs SPY ─────────────────────────────────────
    relative_data = await _get_relative_strength(db, stock_id, close, feats)

    return RLStockSnapshot(
        snapshot_id=snapshot_id,
        symbol=symbol,
        price_data=price_data,
        technical_indicators=tech_dict if tech_dict else None,
        ml_signal=ml_signal_data,
        sentiment=sentiment_data,
        synthesis=synthesis_data,
        analyst_input=analyst_data,
        relative_strength=relative_data,
    )


# ─────────────────────────────────────────────────────────────────────
#  Data fetching helpers
# ─────────────────────────────────────────────────────────────────────

async def _get_price_df(
    db: AsyncSession,
    stock_id: int,
    days: int = 250,
) -> pd.DataFrame | None:
    """Fetch recent OHLCV from prices table, return as DataFrame."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Price)
        .where(Price.stock_id == stock_id, Price.timestamp >= cutoff)
        .order_by(Price.timestamp.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return None

    data = [{
        "timestamp": r.timestamp,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
    } for r in rows]

    df = pd.DataFrame(data)
    df.set_index("timestamp", inplace=True)
    return df


async def _get_latest_ml_signal(db: AsyncSession, stock_id: int) -> dict | None:
    """Get the most recent ML signal for a stock."""
    result = await db.execute(
        select(MLSignal)
        .where(MLSignal.stock_id == stock_id)
        .order_by(MLSignal.created_at.desc())
        .limit(1)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        return None
    return {
        "model_name": sig.model_name,
        "signal": sig.signal,
        "confidence": sig.confidence,
        "feature_importances": sig.feature_importances,
        "created_at": sig.created_at.isoformat() if sig.created_at else None,
    }


async def _get_latest_sentiment(db: AsyncSession, stock_id: int) -> dict | None:
    """Get aggregated recent sentiment for a stock (last 7 days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(NewsAnalysis)
        .join(NewsArticle, NewsArticle.id == NewsAnalysis.article_id)
        .where(
            NewsArticle.stock_id == stock_id,
            NewsArticle.published_at >= cutoff,
        )
        .order_by(NewsArticle.published_at.desc())
    )
    analyses = result.scalars().all()
    if not analyses:
        return None

    scores = [a.sentiment_score for a in analyses]
    material_count = sum(1 for a in analyses if a.material_event)

    return {
        "avg_score": round(sum(scores) / len(scores), 4),
        "min_score": round(min(scores), 4),
        "max_score": round(max(scores), 4),
        "num_articles": len(analyses),
        "material_events": material_count,
        "latest_severity": analyses[0].impact_severity,
    }


async def _get_latest_synthesis(db: AsyncSession, stock_id: int) -> dict | None:
    """Get the most recent context synthesis for a stock."""
    result = await db.execute(
        select(ContextSynthesis)
        .where(ContextSynthesis.stock_id == stock_id)
        .order_by(ContextSynthesis.created_at.desc())
        .limit(1)
    )
    syn = result.scalar_one_or_none()
    if not syn:
        return None
    return {
        "overall_sentiment": syn.overall_sentiment,
        "confidence": syn.confidence,
        "key_factors": syn.key_factors,
        "risks": syn.risks,
        "opportunities": syn.opportunities,
        "created_at": syn.created_at.isoformat() if syn.created_at else None,
    }


async def _get_analyst_input(db: AsyncSession, stock_id: int) -> dict | None:
    """Get active analyst input for a stock."""
    result = await db.execute(
        select(AnalystInput)
        .where(AnalystInput.stock_id == stock_id, AnalystInput.is_active.is_(True))
        .order_by(AnalystInput.updated_at.desc())
        .limit(1)
    )
    inp = result.scalar_one_or_none()
    if not inp:
        return None
    return {
        "conviction": inp.conviction,
        "override_flag": inp.override_flag,
        "time_horizon_days": inp.time_horizon_days,
        "catalysts": inp.catalysts,
    }


async def _get_relative_strength(
    db: AsyncSession,
    stock_id: int,
    current_close: float,
    feats: pd.DataFrame,
) -> dict | None:
    """Compute relative performance vs SPY."""
    spy_result = await db.execute(
        select(Stock.id).where(Stock.symbol == "SPY")
    )
    spy_id = spy_result.scalar_one_or_none()
    if not spy_id:
        return None

    spy_df = await _get_price_df(db, spy_id, days=60)
    if spy_df is None or len(spy_df) < 20:
        return None

    # Stock's 20-day return
    stock_return_20 = feats.iloc[-1].get("return_20d")
    if stock_return_20 is None or (isinstance(stock_return_20, float) and np.isnan(stock_return_20)):
        return None

    # SPY's 20-day return
    spy_close = spy_df["close"]
    spy_return_20 = (spy_close.iloc[-1] / spy_close.iloc[-20] - 1) if len(spy_close) >= 20 else None
    if spy_return_20 is None:
        return None

    return {
        "vs_spy_20d": round(float(stock_return_20) - float(spy_return_20), 6),
    }


# ─────────────────────────────────────────────────────────────────────
#  Snapshot query helpers (for API)
# ─────────────────────────────────────────────────────────────────────

async def get_snapshot_count(db: AsyncSession) -> int:
    """Total number of snapshots."""
    result = await db.execute(
        select(func.count(RLStateSnapshot.id))
    )
    return result.scalar_one()


async def get_latest_snapshot(db: AsyncSession) -> RLStateSnapshot | None:
    """Most recent snapshot."""
    result = await db.execute(
        select(RLStateSnapshot)
        .order_by(RLStateSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_snapshot_date_range(db: AsyncSession) -> dict:
    """First and last snapshot timestamps."""
    result = await db.execute(
        select(
            func.min(RLStateSnapshot.timestamp),
            func.max(RLStateSnapshot.timestamp),
        )
    )
    row = result.one()
    return {
        "first": row[0].isoformat() if row[0] else None,
        "last": row[1].isoformat() if row[1] else None,
    }


async def get_snapshot_stock_coverage(db: AsyncSession) -> dict:
    """Distinct symbols in snapshots and their count."""
    result = await db.execute(
        select(
            RLStockSnapshot.symbol,
            func.count(RLStockSnapshot.id),
        )
        .group_by(RLStockSnapshot.symbol)
        .order_by(func.count(RLStockSnapshot.id).desc())
    )
    rows = result.all()
    return {sym: cnt for sym, cnt in rows}


def _safe_round(val: object, decimals: int = 6) -> float | None:
    """Round a value, returning None for NaN/None."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)) and np.isnan(val):
        return None
    return round(float(val), decimals)
