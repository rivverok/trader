"""Training data API — thin query layer over source tables for the external RL training app.

No snapshots, no copies. The training app queries this API directly over the network
to pull the exact data it needs, with time-range filters.

Endpoints:
  GET /api/training/catalog     — available stocks + date ranges for each data type
  GET /api/training/status      — collection progress, readiness, and training target date
  GET /api/training/prices      — OHLCV price bars (daily or intraday)
  GET /api/training/signals     — ML model signals (buy/sell/hold + confidence)
  GET /api/training/sentiment   — news sentiment scores per stock
  GET /api/training/synthesis   — context synthesis (overall sentiment, confidence, factors)
  GET /api/training/economic    — macro indicators (GDP, CPI, fed funds, VIX, etc.)
  GET /api/training/portfolio   — portfolio snapshots (value, cash, positions, P&L)
  GET /api/training/trades      — executed trade history
"""

from datetime import datetime, date, timedelta, timezone
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.stock import Stock
from app.models.price import Price
from app.models.signal import MLSignal
from app.models.news import NewsArticle
from app.models.analysis import NewsAnalysis, ContextSynthesis
from app.models.economic import EconomicIndicator
from app.models.portfolio import PortfolioSnapshot
from app.models.trade import Trade

router = APIRouter(prefix="/api/training", tags=["training"])

MAX_ROWS = 100_000


# ── Catalog ──────────────────────────────────────────────────────────

@router.get("/catalog")
async def training_catalog(db: AsyncSession = Depends(get_db)):
    """Describe available training data: stocks, date ranges, row counts."""
    stocks_q = await db.execute(
        select(Stock.symbol, Stock.name, Stock.sector).where(Stock.on_watchlist.is_(True)).order_by(Stock.symbol)
    )
    stocks = [{"symbol": r.symbol, "name": r.name, "sector": r.sector} for r in stocks_q.all()]

    prices_q = await db.execute(
        select(func.count(Price.id), func.min(Price.timestamp), func.max(Price.timestamp))
    )
    pr = prices_q.one()

    signals_q = await db.execute(
        select(func.count(MLSignal.id), func.min(MLSignal.created_at), func.max(MLSignal.created_at))
    )
    sg = signals_q.one()

    portfolio_q = await db.execute(
        select(func.count(PortfolioSnapshot.id), func.min(PortfolioSnapshot.timestamp), func.max(PortfolioSnapshot.timestamp))
    )
    pf = portfolio_q.one()

    economic_q = await db.execute(
        select(func.count(EconomicIndicator.id), func.min(EconomicIndicator.date), func.max(EconomicIndicator.date))
    )
    ec = economic_q.one()

    trades_q = await db.execute(select(func.count(Trade.id)))
    tc = trades_q.scalar()

    return {
        "stocks": stocks,
        "prices": {"count": pr[0], "first": pr[1], "last": pr[2]},
        "signals": {"count": sg[0], "first": sg[1], "last": sg[2]},
        "portfolio": {"count": pf[0], "first": pf[1], "last": pf[2]},
        "economic": {"count": ec[0], "first": ec[1], "last": ec[2]},
        "trades": {"count": tc},
    }


# ── Collection Status + Training Readiness ───────────────────────────

# Minimum trading days with data across ALL feature types before training is viable.
MIN_TRAINING_DAYS = 63  # ~3 months
GOOD_TRAINING_DAYS = 126  # ~6 months — recommended target


def _count_trading_days(start: date | None, end: date | None) -> int:
    """Count weekdays between two dates."""
    if not start or not end:
        return 0
    d, count = start, 0
    while d <= end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def _project_date(current_days: int, target_days: int, collection_start: date | None) -> str | None:
    """Project when we'll hit target_days, assuming ~5 trading days per 7 calendar days."""
    if current_days >= target_days:
        return None  # already there
    if not collection_start:
        return None
    remaining = target_days - current_days
    calendar_days = math.ceil(remaining * 7 / 5)
    return (date.today() + timedelta(days=calendar_days)).isoformat()


@router.get("/status")
async def training_status(db: AsyncSession = Depends(get_db)):
    """Collection progress, data quality, and projected training readiness."""

    watchlist_q = await db.execute(
        select(func.count(Stock.id)).where(Stock.on_watchlist.is_(True))
    )
    stock_count = watchlist_q.scalar() or 0

    # ── Per-table stats ──────────────────────────────────────────────
    async def _table_stats(model, ts_col):
        q = await db.execute(
            select(func.count(model.id), func.min(ts_col), func.max(ts_col))
        )
        row = q.one()
        first_ts = row[1]
        last_ts = row[2]
        first_d = first_ts.date() if first_ts else None
        last_d = last_ts.date() if last_ts else None
        return {
            "count": row[0],
            "first": first_ts.isoformat() if first_ts else None,
            "last": last_ts.isoformat() if last_ts else None,
            "trading_days": _count_trading_days(first_d, last_d),
        }

    prices = await _table_stats(Price, Price.timestamp)
    signals = await _table_stats(MLSignal, MLSignal.created_at)
    economic = await _table_stats(EconomicIndicator, EconomicIndicator.date)
    portfolio = await _table_stats(PortfolioSnapshot, PortfolioSnapshot.timestamp)

    # Sentiment: count analyzed articles
    sent_q = await db.execute(
        select(
            func.count(NewsAnalysis.id),
            func.min(NewsArticle.published_at),
            func.max(NewsArticle.published_at),
        )
        .join(NewsArticle, NewsAnalysis.article_id == NewsArticle.id)
    )
    sent_row = sent_q.one()
    sent_first = sent_row[1]
    sent_last = sent_row[2]
    sentiment = {
        "count": sent_row[0],
        "first": sent_first.isoformat() if sent_first else None,
        "last": sent_last.isoformat() if sent_last else None,
        "trading_days": _count_trading_days(
            sent_first.date() if sent_first else None,
            sent_last.date() if sent_last else None,
        ),
    }

    synthesis = await _table_stats(ContextSynthesis, ContextSynthesis.created_at)

    # ── Per-stock coverage (signals per stock) ───────────────────────
    coverage_q = await db.execute(
        select(Stock.symbol, func.count(MLSignal.id))
        .join(MLSignal, MLSignal.stock_id == Stock.id)
        .where(Stock.on_watchlist.is_(True))
        .group_by(Stock.symbol)
        .order_by(Stock.symbol)
    )
    per_stock = {r[0]: r[1] for r in coverage_q.all()}

    # ── Daily collection rate (last 7 days) ──────────────────────────
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    daily_q = await db.execute(
        select(
            cast(Price.timestamp, Date).label("day"),
            func.count(Price.id),
        )
        .where(Price.timestamp >= week_ago)
        .group_by("day")
        .order_by("day")
    )
    daily_prices = [{"date": str(r[0]), "count": r[1]} for r in daily_q.all()]

    # ── Training readiness ───────────────────────────────────────────
    # The binding constraint is the feature type with the fewest trading days
    feature_days = {
        "prices": prices["trading_days"],
        "signals": signals["trading_days"],
        "sentiment": sentiment["trading_days"],
        "synthesis": synthesis["trading_days"],
    }
    min_feature_days = min(feature_days.values()) if feature_days else 0

    # Collection start = earliest first date across derived features
    derived_firsts = []
    for tbl in [signals, sentiment, synthesis]:
        if tbl["first"]:
            derived_firsts.append(tbl["first"][:10])
    collection_start = date.fromisoformat(min(derived_firsts)) if derived_firsts else None

    pct_min = min(100, round(min_feature_days / MIN_TRAINING_DAYS * 100)) if MIN_TRAINING_DAYS else 0
    pct_good = min(100, round(min_feature_days / GOOD_TRAINING_DAYS * 100)) if GOOD_TRAINING_DAYS else 0

    readiness = {
        "min_days_target": MIN_TRAINING_DAYS,
        "good_days_target": GOOD_TRAINING_DAYS,
        "current_days": min_feature_days,
        "feature_days": feature_days,
        "binding_constraint": min(feature_days, key=feature_days.get) if feature_days else None,
        "pct_to_minimum": pct_min,
        "pct_to_recommended": pct_good,
        "ready_minimum": min_feature_days >= MIN_TRAINING_DAYS,
        "ready_recommended": min_feature_days >= GOOD_TRAINING_DAYS,
        "est_minimum_date": _project_date(min_feature_days, MIN_TRAINING_DAYS, collection_start),
        "est_recommended_date": _project_date(min_feature_days, GOOD_TRAINING_DAYS, collection_start),
        "collection_start": collection_start.isoformat() if collection_start else None,
    }

    return {
        "stock_count": stock_count,
        "tables": {
            "prices": prices,
            "signals": signals,
            "sentiment": sentiment,
            "synthesis": synthesis,
            "economic": economic,
            "portfolio": portfolio,
        },
        "per_stock_signals": per_stock,
        "daily_collection_rate": daily_prices,
        "readiness": readiness,
    }


# ── Prices ───────────────────────────────────────────────────────────

@router.get("/prices")
async def training_prices(
    db: AsyncSession = Depends(get_db),
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    interval: str = Query("1Day", description="Bar interval: 1Min, 5Min, 1Day"),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """OHLCV price bars for the given symbols and time range."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    q = (
        select(Stock.symbol, Price.timestamp, Price.open, Price.high, Price.low, Price.close, Price.volume)
        .join(Price, Price.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbol_list),
            Price.interval == interval,
            Price.timestamp >= start,
            Price.timestamp <= end,
        )
        .order_by(Stock.symbol, Price.timestamp)
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "interval": interval,
        "rows": [
            {
                "symbol": r.symbol,
                "timestamp": r.timestamp.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ],
    }


# ── ML Signals ───────────────────────────────────────────────────────

@router.get("/signals")
async def training_signals(
    db: AsyncSession = Depends(get_db),
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """ML model signals (buy/sell/hold, confidence, feature importances)."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    q = (
        select(
            Stock.symbol, MLSignal.created_at, MLSignal.model_name,
            MLSignal.signal, MLSignal.confidence, MLSignal.feature_importances,
        )
        .join(MLSignal, MLSignal.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbol_list),
            MLSignal.created_at >= start,
            MLSignal.created_at <= end,
        )
        .order_by(Stock.symbol, MLSignal.created_at)
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "symbol": r.symbol,
                "timestamp": r.created_at.isoformat(),
                "model": r.model_name,
                "signal": r.signal,
                "confidence": r.confidence,
                "feature_importances": r.feature_importances,
            }
            for r in rows
        ],
    }


# ── Sentiment ────────────────────────────────────────────────────────

@router.get("/sentiment")
async def training_sentiment(
    db: AsyncSession = Depends(get_db),
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """News sentiment analysis scores per stock."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    q = (
        select(
            Stock.symbol, NewsArticle.published_at, NewsArticle.headline,
            NewsAnalysis.sentiment_score, NewsAnalysis.impact_severity,
            NewsAnalysis.material_event, NewsAnalysis.summary,
        )
        .join(NewsArticle, NewsArticle.stock_id == Stock.id)
        .join(NewsAnalysis, NewsAnalysis.article_id == NewsArticle.id)
        .where(
            Stock.symbol.in_(symbol_list),
            NewsArticle.published_at >= start,
            NewsArticle.published_at <= end,
        )
        .order_by(Stock.symbol, NewsArticle.published_at)
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "symbol": r.symbol,
                "timestamp": r.published_at.isoformat(),
                "headline": r.headline,
                "sentiment_score": r.sentiment_score,
                "impact_severity": r.impact_severity,
                "material_event": r.material_event,
                "summary": r.summary,
            }
            for r in rows
        ],
    }


# ── Context Synthesis ────────────────────────────────────────────────

@router.get("/synthesis")
async def training_synthesis(
    db: AsyncSession = Depends(get_db),
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """Context synthesis records (overall sentiment, confidence, key factors)."""
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    q = (
        select(
            Stock.symbol, ContextSynthesis.created_at,
            ContextSynthesis.overall_sentiment, ContextSynthesis.confidence,
            ContextSynthesis.key_factors, ContextSynthesis.risks,
            ContextSynthesis.opportunities,
        )
        .join(ContextSynthesis, ContextSynthesis.stock_id == Stock.id)
        .where(
            Stock.symbol.in_(symbol_list),
            ContextSynthesis.created_at >= start,
            ContextSynthesis.created_at <= end,
        )
        .order_by(Stock.symbol, ContextSynthesis.created_at)
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "symbol": r.symbol,
                "timestamp": r.created_at.isoformat(),
                "overall_sentiment": r.overall_sentiment,
                "confidence": r.confidence,
                "key_factors": r.key_factors,
                "risks": r.risks,
                "opportunities": r.opportunities,
            }
            for r in rows
        ],
    }


# ── Economic Indicators ──────────────────────────────────────────────

@router.get("/economic")
async def training_economic(
    db: AsyncSession = Depends(get_db),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    indicators: str | None = Query(None, description="Comma-separated indicator codes (e.g. GDP,CPI). Omit for all."),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """Macro-economic indicators from FRED."""
    q = (
        select(
            EconomicIndicator.indicator_code, EconomicIndicator.name,
            EconomicIndicator.date, EconomicIndicator.value,
        )
        .where(
            EconomicIndicator.date >= start,
            EconomicIndicator.date <= end,
        )
    )
    if indicators:
        codes = [c.strip().upper() for c in indicators.split(",")]
        q = q.where(EconomicIndicator.indicator_code.in_(codes))
    q = q.order_by(EconomicIndicator.indicator_code, EconomicIndicator.date).limit(limit)
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "indicator": r.indicator_code,
                "name": r.name,
                "date": r.date.isoformat(),
                "value": r.value,
            }
            for r in rows
        ],
    }


# ── Portfolio ────────────────────────────────────────────────────────

@router.get("/portfolio")
async def training_portfolio(
    db: AsyncSession = Depends(get_db),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """Portfolio snapshots (total value, cash, positions value, P&L)."""
    q = (
        select(
            PortfolioSnapshot.timestamp, PortfolioSnapshot.total_value,
            PortfolioSnapshot.cash, PortfolioSnapshot.positions_value,
            PortfolioSnapshot.daily_pnl, PortfolioSnapshot.cumulative_pnl,
        )
        .where(
            PortfolioSnapshot.timestamp >= start,
            PortfolioSnapshot.timestamp <= end,
        )
        .order_by(PortfolioSnapshot.timestamp)
        .limit(limit)
    )
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "timestamp": r.timestamp.isoformat(),
                "total_value": r.total_value,
                "cash": r.cash,
                "positions_value": r.positions_value,
                "daily_pnl": r.daily_pnl,
                "cumulative_pnl": r.cumulative_pnl,
            }
            for r in rows
        ],
    }


# ── Trades ───────────────────────────────────────────────────────────

@router.get("/trades")
async def training_trades(
    db: AsyncSession = Depends(get_db),
    start: datetime = Query(..., description="Start datetime (inclusive)"),
    end: datetime = Query(..., description="End datetime (inclusive)"),
    symbols: str | None = Query(None, description="Comma-separated stock symbols. Omit for all."),
    limit: int = Query(MAX_ROWS, le=MAX_ROWS),
):
    """Executed trades (action, shares, prices, P&L)."""
    q = (
        select(
            Stock.symbol, Trade.created_at, Trade.action,
            Trade.shares, Trade.fill_price, Trade.pnl,
        )
        .join(Stock, Trade.stock_id == Stock.id)
        .where(
            Trade.created_at >= start,
            Trade.created_at <= end,
        )
    )
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        q = q.where(Stock.symbol.in_(symbol_list))
    q = q.order_by(Trade.created_at).limit(limit)
    result = await db.execute(q)
    rows = result.all()
    return {
        "count": len(rows),
        "rows": [
            {
                "symbol": r.symbol,
                "timestamp": r.created_at.isoformat(),
                "action": r.action,
                "shares": r.shares,
                "fill_price": r.fill_price,
                "pnl": r.pnl,
            }
            for r in rows
        ],
    }
