"""Alpaca Markets collector — stock metadata, OHLCV bars, and account info."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import BaseCollector
from app.config import settings
from app.models.price import Price
from app.models.stock import Stock


class AlpacaCollector(BaseCollector):
    name = "alpaca"
    max_requests_per_minute = 200  # Alpaca allows 200/min

    def __init__(self):
        super().__init__()
        self.base_url = settings.ALPACA_BASE_URL
        self.data_url = "https://data.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
        }

    # ── Public API ────────────────────────────────────────────────────

    async def collect(self, **kwargs) -> dict[str, Any]:
        """Collect latest bars for all watchlist stocks."""
        async with self._build_client(headers=self.headers) as client:
            session: AsyncSession = kwargs["db_session"]
            stocks = await self._get_watchlist_stocks(session)
            if not stocks:
                return {"status": "skip", "reason": "no watchlist stocks"}

            symbols = [s.symbol for s in stocks]
            symbol_to_id = {s.symbol: s.id for s in stocks}

            bars = await self._fetch_latest_bars(client, symbols)
            inserted = await self._store_bars(session, bars, symbol_to_id, interval="1Min")

            return {"status": "ok", "symbols": len(symbols), "bars_inserted": inserted}

    async def collect_daily_bars(self, db_session: AsyncSession) -> dict[str, Any]:
        """Collect end-of-day bars for today."""
        async with self._build_client(headers=self.headers) as client:
            stocks = await self._get_watchlist_stocks(db_session)
            if not stocks:
                return {"status": "skip", "reason": "no watchlist stocks"}

            symbols = [s.symbol for s in stocks]
            symbol_to_id = {s.symbol: s.id for s in stocks}

            today = datetime.now(timezone.utc).date()
            bars = await self._fetch_bars(
                client, symbols, timeframe="1Day",
                start=(today - timedelta(days=1)).isoformat(),
                end=today.isoformat(),
            )
            inserted = await self._store_bars(db_session, bars, symbol_to_id, interval="1Day")
            return {"status": "ok", "symbols": len(symbols), "bars_inserted": inserted}

    async def backfill_historical(
        self, db_session: AsyncSession, years: int = 5
    ) -> dict[str, Any]:
        """Backfill daily bars for all watchlist stocks going back `years` years."""
        async with self._build_client(headers=self.headers) as client:
            stocks = await self._get_watchlist_stocks(db_session)
            if not stocks:
                return {"status": "skip", "reason": "no watchlist stocks"}

            symbol_to_id = {s.symbol: s.id for s in stocks}
            total_inserted = 0
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=365 * years)

            for stock in stocks:
                self.logger.info("Backfilling %s from %s to %s", stock.symbol, start, end)
                bars = await self._fetch_bars(
                    client, [stock.symbol], timeframe="1Day",
                    start=start.isoformat(), end=end.isoformat(),
                )
                inserted = await self._store_bars(
                    db_session, bars, symbol_to_id, interval="1Day"
                )
                total_inserted += inserted
                self.logger.info("Backfilled %d bars for %s", inserted, stock.symbol)

            return {"status": "ok", "symbols": len(stocks), "bars_inserted": total_inserted}

    async def fetch_stock_info(self, symbol: str) -> dict[str, Any]:
        """Fetch asset info from Alpaca to populate stock metadata."""
        async with self._build_client(headers=self.headers) as client:
            resp = await self._request_with_retry(
                client, "GET",
                f"{self.base_url}/v2/assets/{symbol.upper()}",
            )
            data = resp.json()
            return {
                "symbol": data.get("symbol", symbol.upper()),
                "name": data.get("name", ""),
                "exchange": data.get("exchange", ""),
                "sector": "",  # Alpaca doesn't provide sector
                "industry": "",
            }

    # ── Internal helpers ──────────────────────────────────────────────

    async def _get_watchlist_stocks(self, session: AsyncSession) -> list[Stock]:
        result = await session.execute(
            select(Stock).where(Stock.on_watchlist.is_(True))
        )
        return list(result.scalars().all())

    async def _fetch_latest_bars(
        self, client, symbols: list[str]
    ) -> dict[str, list[dict]]:
        """Fetch the latest bar for each symbol."""
        params = {"symbols": ",".join(symbols), "timeframe": "1Min", "limit": 1}
        resp = await self._request_with_retry(
            client, "GET", f"{self.data_url}/v2/stocks/bars/latest", params=params,
        )
        data = resp.json()
        return data.get("bars", {})

    async def _fetch_bars(
        self,
        client,
        symbols: list[str],
        timeframe: str = "1Day",
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, list[dict]]:
        """Fetch historical bars with pagination."""
        all_bars: dict[str, list[dict]] = {}
        page_token = None

        while True:
            params: dict[str, Any] = {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "limit": 10000,
            }
            if start:
                params["start"] = start
            if end:
                params["end"] = end
            if page_token:
                params["page_token"] = page_token

            resp = await self._request_with_retry(
                client, "GET", f"{self.data_url}/v2/stocks/bars", params=params,
            )
            data = resp.json()

            for sym, bars in data.get("bars", {}).items():
                all_bars.setdefault(sym, []).extend(bars)

            page_token = data.get("next_page_token")
            if not page_token:
                break

        return all_bars

    async def _store_bars(
        self,
        session: AsyncSession,
        bars: dict[str, list[dict] | dict],
        symbol_to_id: dict[str, int],
        interval: str,
    ) -> int:
        """Upsert bars into the prices table. Returns count of rows inserted."""
        rows = []
        for symbol, bar_list in bars.items():
            stock_id = symbol_to_id.get(symbol)
            if stock_id is None:
                continue
            # Latest bars endpoint returns a single dict, not a list
            if isinstance(bar_list, dict):
                bar_list = [bar_list]
            for bar in bar_list:
                rows.append({
                    "stock_id": stock_id,
                    "timestamp": bar["t"],
                    "open": float(bar["o"]),
                    "high": float(bar["h"]),
                    "low": float(bar["l"]),
                    "close": float(bar["c"]),
                    "volume": int(bar["v"]),
                    "interval": interval,
                })

        if not rows:
            return 0

        # Use ON CONFLICT DO NOTHING to handle duplicate (stock_id, timestamp) pairs
        stmt = pg_insert(Price).values(rows).on_conflict_do_nothing()
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount  # type: ignore[return-value]
