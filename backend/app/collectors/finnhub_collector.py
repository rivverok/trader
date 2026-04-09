"""Finnhub collector — company news and profiles."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import BaseCollector
from app.config import settings
from app.models.news import NewsArticle
from app.models.stock import Stock


class FinnhubCollector(BaseCollector):
    name = "finnhub"
    max_requests_per_minute = 55  # Free tier = 60/min, leave a buffer

    def __init__(self):
        super().__init__()
        self.base_url = "https://finnhub.io/api/v1"
        self.api_key = settings.FINNHUB_API_KEY

    # ── Public API ────────────────────────────────────────────────────

    async def collect(self, **kwargs) -> dict[str, Any]:
        """Collect news articles for all watchlist stocks."""
        db_session: AsyncSession = kwargs["db_session"]
        stocks = await self._get_watchlist_stocks(db_session)
        if not stocks:
            return {"status": "skip", "reason": "no watchlist stocks"}

        total_inserted = 0
        async with self._build_client() as client:
            for stock in stocks:
                articles = await self._fetch_news(client, stock.symbol)
                inserted = await self._store_articles(db_session, articles, stock.id)
                total_inserted += inserted
                self.logger.info(
                    "Collected %d new articles for %s", inserted, stock.symbol
                )

        return {"status": "ok", "symbols": len(stocks), "articles_inserted": total_inserted}

    async def fetch_company_profile(self, symbol: str) -> dict[str, Any]:
        """Fetch company profile to fill in sector/industry."""
        async with self._build_client() as client:
            resp = await self._request_with_retry(
                client, "GET",
                f"{self.base_url}/stock/profile2",
                params={"symbol": symbol.upper(), "token": self.api_key},
            )
            data = resp.json()
            return {
                "name": data.get("name", ""),
                "sector": data.get("finnhubIndustry", ""),
                "exchange": data.get("exchange", ""),
            }

    # ── Internal helpers ──────────────────────────────────────────────

    async def _get_watchlist_stocks(self, session: AsyncSession) -> list[Stock]:
        result = await session.execute(
            select(Stock).where(Stock.on_watchlist.is_(True))
        )
        return list(result.scalars().all())

    async def _fetch_news(
        self, client, symbol: str, days_back: int = 7
    ) -> list[dict]:
        """Fetch company news from Finnhub for the last N days."""
        today = datetime.now(timezone.utc).date()
        from_date = (today - timedelta(days=days_back)).isoformat()
        to_date = today.isoformat()

        resp = await self._request_with_retry(
            client, "GET",
            f"{self.base_url}/company-news",
            params={
                "symbol": symbol.upper(),
                "from": from_date,
                "to": to_date,
                "token": self.api_key,
            },
        )
        return resp.json()  # list of article dicts

    async def _store_articles(
        self, session: AsyncSession, articles: list[dict], stock_id: int
    ) -> int:
        """Insert articles, deduplicating by URL. Returns count inserted."""
        if not articles:
            return 0

        rows = []
        for article in articles:
            url = article.get("url", "")
            if not url:
                continue
            rows.append({
                "stock_id": stock_id,
                "headline": (article.get("headline", "") or "")[:500],
                "summary": article.get("summary"),
                "source": (article.get("source", "") or "")[:100],
                "url": url[:1000],
                "published_at": datetime.fromtimestamp(
                    article.get("datetime", 0), tz=timezone.utc
                ),
                "raw_content": article.get("summary"),
                "sentiment_score": None,
                "analyzed": False,
            })

        if not rows:
            return 0

        stmt = pg_insert(NewsArticle).values(rows).on_conflict_do_nothing(
            index_elements=["url"]
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount  # type: ignore[return-value]
