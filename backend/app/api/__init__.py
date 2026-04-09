"""API routes for stock management and price/news queries."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.news import NewsArticle
from app.models.price import Price
from app.models.stock import Stock

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


# ── Schemas ──────────────────────────────────────────────────────────

class StockCreate(BaseModel):
    symbol: str


class StockResponse(BaseModel):
    id: int
    symbol: str
    name: str | None
    sector: str | None
    industry: str | None
    exchange: str | None
    on_watchlist: bool
    latest_price: float | None = None
    daily_change_pct: float | None = None

    model_config = {"from_attributes": True}


class PriceResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class NewsResponse(BaseModel):
    id: int
    headline: str
    summary: str | None
    source: str | None
    url: str
    published_at: str
    sentiment_score: float | None
    analyzed: bool

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=list[StockResponse])
async def list_stocks(
    watchlist: Optional[bool] = Query(None, description="Filter by watchlist status"),
    db: AsyncSession = Depends(get_db),
):
    """List all stocks, optionally filtered to watchlist only."""
    query = select(Stock)
    if watchlist is not None:
        query = query.where(Stock.on_watchlist == watchlist)
    query = query.order_by(Stock.symbol)

    result = await db.execute(query)
    stocks = result.scalars().all()

    # Enrich with latest price + daily change
    response = []
    for stock in stocks:
        latest_price, daily_change = await _get_latest_price_info(db, stock.id)
        resp = StockResponse(
            id=stock.id,
            symbol=stock.symbol,
            name=stock.name,
            sector=stock.sector,
            industry=stock.industry,
            exchange=stock.exchange,
            on_watchlist=stock.on_watchlist,
            latest_price=latest_price,
            daily_change_pct=daily_change,
        )
        response.append(resp)

    return response


@router.post("", response_model=StockResponse, status_code=201)
async def add_stock(
    payload: StockCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a stock to the system. Auto-fetches metadata from Alpaca/Finnhub."""
    symbol = payload.symbol.upper().strip()
    if not symbol or len(symbol) > 10:
        raise HTTPException(400, "Invalid symbol")

    # Check if already exists
    existing = await db.execute(select(Stock).where(Stock.symbol == symbol))
    if existing.scalars().first():
        raise HTTPException(409, f"{symbol} already exists")

    # Fetch metadata from Alpaca
    try:
        from app.collectors.alpaca_collector import AlpacaCollector
        info = await AlpacaCollector().fetch_stock_info(symbol)
    except Exception:
        info = {"symbol": symbol, "name": "", "exchange": "", "sector": "", "industry": ""}

    # Enrich with Finnhub sector/industry
    try:
        from app.collectors.finnhub_collector import FinnhubCollector
        profile = await FinnhubCollector().fetch_company_profile(symbol)
        if profile.get("name"):
            info["name"] = info["name"] or profile["name"]
        if profile.get("sector"):
            info["sector"] = profile["sector"]
    except Exception:
        pass

    stock = Stock(
        symbol=symbol,
        name=info.get("name", ""),
        sector=info.get("sector", ""),
        industry=info.get("industry", ""),
        exchange=info.get("exchange", ""),
        on_watchlist=True,
    )
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    return StockResponse(
        id=stock.id,
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        industry=stock.industry,
        exchange=stock.exchange,
        on_watchlist=stock.on_watchlist,
    )


@router.delete("/{symbol}", status_code=204)
async def remove_stock(symbol: str, db: AsyncSession = Depends(get_db)):
    """Remove a stock from the watchlist (soft-delete — sets on_watchlist=False)."""
    result = await db.execute(
        select(Stock).where(Stock.symbol == symbol.upper())
    )
    stock = result.scalars().first()
    if not stock:
        raise HTTPException(404, f"{symbol} not found")
    stock.on_watchlist = False
    await db.commit()


@router.get("/{symbol}/prices", response_model=list[PriceResponse])
async def get_stock_prices(
    symbol: str,
    interval: str = Query("1Day", description="Bar interval: 1Min, 5Min, 1Day"),
    start: Optional[str] = Query(None, description="ISO date start"),
    end: Optional[str] = Query(None, description="ISO date end"),
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
):
    """Get price history for a stock."""
    stock = await _get_stock_or_404(db, symbol)

    query = (
        select(Price)
        .where(Price.stock_id == stock.id, Price.interval == interval)
        .order_by(desc(Price.timestamp))
        .limit(limit)
    )

    if start:
        query = query.where(Price.timestamp >= start)
    if end:
        query = query.where(Price.timestamp <= end)

    result = await db.execute(query)
    prices = result.scalars().all()

    return [
        PriceResponse(
            timestamp=p.timestamp.isoformat(),
            open=p.open,
            high=p.high,
            low=p.low,
            close=p.close,
            volume=p.volume,
        )
        for p in reversed(prices)  # oldest first
    ]


@router.get("/{symbol}/news", response_model=list[NewsResponse])
async def get_stock_news(
    symbol: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get recent news articles for a stock."""
    stock = await _get_stock_or_404(db, symbol)

    result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.stock_id == stock.id)
        .order_by(desc(NewsArticle.published_at))
        .limit(limit)
    )
    articles = result.scalars().all()

    return [
        NewsResponse(
            id=a.id,
            headline=a.headline,
            summary=a.summary,
            source=a.source,
            url=a.url,
            published_at=a.published_at.isoformat(),
            sentiment_score=a.sentiment_score,
            analyzed=a.analyzed,
        )
        for a in articles
    ]


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_stock_or_404(db: AsyncSession, symbol: str) -> Stock:
    result = await db.execute(
        select(Stock).where(Stock.symbol == symbol.upper())
    )
    stock = result.scalars().first()
    if not stock:
        raise HTTPException(404, f"Stock {symbol} not found")
    return stock


async def _get_latest_price_info(
    db: AsyncSession, stock_id: int
) -> tuple[float | None, float | None]:
    """Return (latest_close, daily_change_pct) for a stock."""
    result = await db.execute(
        select(Price)
        .where(Price.stock_id == stock_id, Price.interval == "1Day")
        .order_by(desc(Price.timestamp))
        .limit(2)
    )
    prices = result.scalars().all()

    if not prices:
        return None, None

    latest = prices[0].close
    if len(prices) >= 2:
        prev = prices[1].close
        change = ((latest - prev) / prev) * 100 if prev else None
    else:
        change = None

    return latest, round(change, 2) if change is not None else None
