"""Backfill RL state snapshots from historical data.

Reconstructs state snapshots for every trading day where we have daily price bars.
Re-uses the same logic as state_snapshots.py, but operates on historical dates
rather than "now".

Usage:
    # In the backend container:
    python -m scripts.backfill_snapshots

    # Or from repo root with correct PYTHONPATH:
    cd backend && python -m scripts.backfill_snapshots [--start 2024-01-01] [--end 2025-04-10]

Idempotent — skips dates that already have a 'backfill' snapshot.
"""

import argparse
import asyncio
import logging
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Ensure backend package is importable ─────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database import async_session
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

MIN_PRICE_ROWS = 50  # Need enough history for indicators


# ─────────────────────────────────────────────────────────────────────
#  Main backfill loop
# ─────────────────────────────────────────────────────────────────────


async def backfill(start_date: date | None = None, end_date: date | None = None):
    """Reconstruct snapshots for every trading day in the date range."""

    async with async_session() as db:
        # ── Discover date range from price data ──────────────────────
        if start_date is None:
            result = await db.execute(
                select(func.min(func.date(Price.timestamp)))
            )
            start_date = result.scalar_one_or_none()
            if start_date is None:
                logger.error("No price data found — nothing to backfill")
                return

        if end_date is None:
            result = await db.execute(
                select(func.max(func.date(Price.timestamp)))
            )
            end_date = result.scalar_one_or_none()
            if end_date is None:
                logger.error("No price data found — nothing to backfill")
                return

        # ── Get all distinct trading dates ───────────────────────────
        result = await db.execute(
            select(func.date(Price.timestamp).label("d"))
            .where(
                func.date(Price.timestamp) >= start_date,
                func.date(Price.timestamp) <= end_date,
            )
            .distinct()
            .order_by("d")
        )
        all_dates: list[date] = [row[0] for row in result.all()]
        logger.info(
            "Found %d trading days from %s to %s", len(all_dates), start_date, end_date
        )

        # ── Find dates that already have backfill snapshots ──────────
        result = await db.execute(
            select(func.date(RLStateSnapshot.timestamp))
            .where(RLStateSnapshot.snapshot_type == "backfill")
        )
        existing_dates: set[date] = {row[0] for row in result.all()}
        remaining = [d for d in all_dates if d not in existing_dates]
        logger.info(
            "Skipping %d already-backfilled dates, %d remaining",
            len(all_dates) - len(remaining),
            len(remaining),
        )

        # ── Get watchlist stocks ─────────────────────────────────────
        result = await db.execute(
            select(Stock).where(Stock.on_watchlist.is_(True))
        )
        watchlist_stocks: list[Stock] = list(result.scalars().all())
        if not watchlist_stocks:
            logger.error("No watchlist stocks — nothing to backfill")
            return
        logger.info("Processing %d watchlist stocks", len(watchlist_stocks))

        # ── Process each date ────────────────────────────────────────
        total_created = 0
        for i, target_date in enumerate(remaining):
            # Use market close time (20:00 UTC ≈ 4pm ET) as snapshot timestamp
            snapshot_ts = datetime.combine(
                target_date, datetime.min.time()
            ).replace(hour=20, tzinfo=timezone.utc)

            try:
                snapshot = await _build_snapshot_for_date(
                    db, snapshot_ts, target_date, watchlist_stocks
                )
                if snapshot:
                    total_created += 1
            except Exception:
                logger.exception("Failed to build snapshot for %s", target_date)
                continue

            if (i + 1) % 50 == 0:
                logger.info(
                    "Progress: %d / %d dates processed (%d snapshots created)",
                    i + 1, len(remaining), total_created,
                )

        logger.info(
            "Backfill complete: %d snapshots created from %d dates",
            total_created, len(remaining),
        )


# ─────────────────────────────────────────────────────────────────────
#  Build a single historical snapshot
# ─────────────────────────────────────────────────────────────────────


async def _build_snapshot_for_date(
    db: AsyncSession,
    snapshot_ts: datetime,
    target_date: date,
    stocks: list[Stock],
) -> RLStateSnapshot | None:
    """Build and persist a state snapshot for a specific historical date."""

    # ── Portfolio state (nearest portfolio snapshot) ──────────────────
    portfolio_state = await _build_historical_portfolio_state(db, snapshot_ts)

    # ── Market state ─────────────────────────────────────────────────
    market_state = await _build_historical_market_state(db, snapshot_ts, target_date)

    # ── Create the parent snapshot record ────────────────────────────
    snapshot = RLStateSnapshot(
        timestamp=snapshot_ts,
        snapshot_type="backfill",
        portfolio_state=portfolio_state,
        market_state=market_state,
        metadata_={
            "source": "backfill_script",
            "target_date": target_date.isoformat(),
        },
    )
    db.add(snapshot)
    await db.flush()  # Get snapshot.id

    # ── Per-stock snapshots ──────────────────────────────────────────
    stock_count = 0
    for stock in stocks:
        stock_snap = await _build_historical_stock_snapshot(
            db, snapshot.id, stock, snapshot_ts, target_date
        )
        if stock_snap:
            db.add(stock_snap)
            stock_count += 1

    if stock_count == 0:
        # No usable stock data for this date — roll back
        await db.rollback()
        logger.debug("No stock data for %s — skipped", target_date)
        return None

    await db.commit()
    logger.debug("Created snapshot for %s with %d stocks", target_date, stock_count)
    return snapshot


# ─────────────────────────────────────────────────────────────────────
#  Portfolio state (historical)
# ─────────────────────────────────────────────────────────────────────


async def _build_historical_portfolio_state(
    db: AsyncSession, snapshot_ts: datetime
) -> dict:
    """Get nearest portfolio snapshot to the target timestamp."""
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.timestamp <= snapshot_ts)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        return {
            "total_value": 0,
            "cash": 0,
            "positions_value": 0,
            "cash_pct": 1.0,
            "num_positions": 0,
            "total_exposure_pct": 0.0,
            "largest_position_pct": 0.0,
            "daily_pnl": 0.0,
            "daily_pnl_pct": 0.0,
            "cumulative_pnl": 0.0,
            "unrealized_pnl_total": 0.0,
            "sector_weights": {},
            "positions": [],
        }

    total = snap.total_value or 0
    return {
        "total_value": total,
        "cash": snap.cash,
        "positions_value": snap.positions_value,
        "cash_pct": round(snap.cash / total, 4) if total > 0 else 1.0,
        "num_positions": 0,  # backfill doesn't track individual positions per day
        "total_exposure_pct": round(snap.positions_value / total * 100, 4)
        if total > 0
        else 0.0,
        "largest_position_pct": 0.0,
        "daily_pnl": snap.daily_pnl,
        "daily_pnl_pct": round(snap.daily_pnl / total * 100, 4) if total > 0 else 0.0,
        "cumulative_pnl": snap.cumulative_pnl,
        "unrealized_pnl_total": 0.0,
        "sector_weights": {},
        "positions": [],
    }


# ─────────────────────────────────────────────────────────────────────
#  Market state (historical)
# ─────────────────────────────────────────────────────────────────────


async def _build_historical_market_state(
    db: AsyncSession, snapshot_ts: datetime, target_date: date
) -> dict:
    """Build market-level features from historical data."""
    market: dict = {}

    # ── SPY data ─────────────────────────────────────────────────────
    spy_result = await db.execute(select(Stock).where(Stock.symbol == "SPY"))
    spy_stock = spy_result.scalar_one_or_none()

    if spy_stock:
        spy_prices = await _get_historical_price_df(
            db, spy_stock.id, target_date, days=250
        )
        if spy_prices is not None and len(spy_prices) >= 50:
            feats = compute_features(spy_prices)
            if not feats.empty:
                last = feats.iloc[-1]
                close = last["close"]
                sma50 = last.get("sma_50")
                sma200 = last.get("sma_200")
                market["spy_close"] = close
                market["spy_vs_sma50"] = (
                    round((close / sma50) - 1, 6)
                    if sma50 and not pd.isna(sma50)
                    else None
                )
                market["spy_vs_sma200"] = (
                    round((close / sma200) - 1, 6)
                    if sma200 and not pd.isna(sma200)
                    else None
                )
                market["spy_return_5d"] = _safe_round(last.get("return_5d"))
                market["spy_return_20d"] = _safe_round(last.get("return_20d"))

    # ── Economic indicators (latest as of target date) ───────────────
    eco_codes = ["FEDFUNDS", "GS10", "GS2", "CPIAUCSL", "UNRATE", "VIXCLS"]
    for code in eco_codes:
        result = await db.execute(
            select(EconomicIndicator)
            .where(
                EconomicIndicator.indicator_code == code,
                EconomicIndicator.date <= snapshot_ts,
            )
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

    vix = market.get("vixcls")
    if vix is not None:
        market["vix_normalized"] = round(vix / 30.0, 4)

    # ── Calendar features ────────────────────────────────────────────
    market["day_of_week"] = target_date.weekday()
    market["month"] = target_date.month
    market["month_sin"] = round(math.sin(2 * math.pi * target_date.month / 12), 6)
    market["month_cos"] = round(math.cos(2 * math.pi * target_date.month / 12), 6)

    return market


# ─────────────────────────────────────────────────────────────────────
#  Per-stock historical snapshot
# ─────────────────────────────────────────────────────────────────────


async def _build_historical_stock_snapshot(
    db: AsyncSession,
    snapshot_id: int,
    stock: Stock,
    snapshot_ts: datetime,
    target_date: date,
) -> RLStockSnapshot | None:
    """Build a stock snapshot from data available up to target_date."""
    symbol = stock.symbol
    stock_id = stock.id

    # ── Price data + technicals ──────────────────────────────────────
    price_df = await _get_historical_price_df(db, stock_id, target_date, days=250)
    if price_df is None or len(price_df) < MIN_PRICE_ROWS:
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

    # All computed indicators
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

    # ── ML signal (nearest before target date) ───────────────────────
    ml_signal_data = await _get_nearest_ml_signal(db, stock_id, snapshot_ts)

    # ── Sentiment (7 days before target date) ────────────────────────
    sentiment_data = await _get_nearest_sentiment(db, stock_id, snapshot_ts)

    # ── Synthesis (nearest before target date) ───────────────────────
    synthesis_data = await _get_nearest_synthesis(db, stock_id, snapshot_ts)

    # ── Analyst input (active as of target date) ─────────────────────
    analyst_data = await _get_nearest_analyst_input(db, stock_id, snapshot_ts)

    # ── Relative strength vs SPY ─────────────────────────────────────
    relative_data = await _get_historical_relative_strength(
        db, stock_id, close, feats, target_date
    )

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
#  Historical data fetching helpers
# ─────────────────────────────────────────────────────────────────────


async def _get_historical_price_df(
    db: AsyncSession, stock_id: int, target_date: date, days: int = 250
) -> pd.DataFrame | None:
    """Fetch OHLCV up to and including target_date."""
    cutoff = target_date - timedelta(days=days)
    result = await db.execute(
        select(Price)
        .where(
            Price.stock_id == stock_id,
            func.date(Price.timestamp) >= cutoff,
            func.date(Price.timestamp) <= target_date,
        )
        .order_by(Price.timestamp.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return None

    data = [
        {
            "timestamp": r.timestamp,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]
    df = pd.DataFrame(data)
    df.set_index("timestamp", inplace=True)
    return df


async def _get_nearest_ml_signal(
    db: AsyncSession, stock_id: int, before: datetime
) -> dict | None:
    """Get ML signal nearest to (but not after) the target timestamp."""
    result = await db.execute(
        select(MLSignal)
        .where(MLSignal.stock_id == stock_id, MLSignal.created_at <= before)
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


async def _get_nearest_sentiment(
    db: AsyncSession, stock_id: int, before: datetime
) -> dict | None:
    """Get aggregated sentiment from 7 days before the target timestamp."""
    cutoff = before - timedelta(days=7)
    result = await db.execute(
        select(NewsAnalysis)
        .join(NewsArticle, NewsArticle.id == NewsAnalysis.article_id)
        .where(
            NewsArticle.stock_id == stock_id,
            NewsArticle.published_at >= cutoff,
            NewsArticle.published_at <= before,
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


async def _get_nearest_synthesis(
    db: AsyncSession, stock_id: int, before: datetime
) -> dict | None:
    """Get synthesis nearest to (but not after) the target timestamp."""
    result = await db.execute(
        select(ContextSynthesis)
        .where(
            ContextSynthesis.stock_id == stock_id,
            ContextSynthesis.created_at <= before,
        )
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


async def _get_nearest_analyst_input(
    db: AsyncSession, stock_id: int, before: datetime
) -> dict | None:
    """Get analyst input active as of the target timestamp."""
    result = await db.execute(
        select(AnalystInput)
        .where(
            AnalystInput.stock_id == stock_id,
            AnalystInput.is_active.is_(True),
            AnalystInput.created_at <= before,
        )
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


async def _get_historical_relative_strength(
    db: AsyncSession,
    stock_id: int,
    current_close: float,
    feats: pd.DataFrame,
    target_date: date,
) -> dict | None:
    """Compute relative performance vs SPY as of target_date."""
    spy_result = await db.execute(select(Stock.id).where(Stock.symbol == "SPY"))
    spy_id = spy_result.scalar_one_or_none()
    if not spy_id:
        return None

    spy_df = await _get_historical_price_df(db, spy_id, target_date, days=60)
    if spy_df is None or len(spy_df) < 20:
        return None

    stock_return_20 = feats.iloc[-1].get("return_20d")
    if stock_return_20 is None or (
        isinstance(stock_return_20, float) and np.isnan(stock_return_20)
    ):
        return None

    spy_close = spy_df["close"]
    spy_return_20 = (
        (spy_close.iloc[-1] / spy_close.iloc[-20] - 1) if len(spy_close) >= 20 else None
    )
    if spy_return_20 is None:
        return None

    return {
        "vs_spy_20d": round(float(stock_return_20) - float(spy_return_20), 6),
    }


def _safe_round(val: object, decimals: int = 6) -> float | None:
    if val is None:
        return None
    if isinstance(val, (float, np.floating)) and np.isnan(val):
        return None
    return round(float(val), decimals)


# ─────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Backfill RL state snapshots")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    asyncio.run(backfill(start, end))


if __name__ == "__main__":
    main()
