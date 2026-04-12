"""Training data API — thin query layer over source tables for the external RL training app.

No snapshots, no copies. The training app queries this API directly over the network
to pull the exact data it needs, with time-range filters.

Endpoints:
  GET /api/training/catalog     — available stocks + date ranges for each data type
  GET /api/training/prices      — OHLCV price bars (daily or intraday)
  GET /api/training/signals     — ML model signals (buy/sell/hold + confidence)
  GET /api/training/sentiment   — news sentiment scores per stock
  GET /api/training/synthesis   — context synthesis (overall sentiment, confidence, factors)
  GET /api/training/economic    — macro indicators (GDP, CPI, fed funds, VIX, etc.)
  GET /api/training/portfolio   — portfolio snapshots (value, cash, positions, P&L)
  GET /api/training/trades      — executed trade history
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
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
