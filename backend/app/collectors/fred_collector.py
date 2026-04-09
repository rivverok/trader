"""FRED (Federal Reserve Economic Data) collector — key economic indicators."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import BaseCollector
from app.config import settings
from app.models.economic import EconomicIndicator

# Series IDs for key economic indicators
FRED_SERIES = {
    "GDP": "Real Gross Domestic Product",
    "CPIAUCSL": "Consumer Price Index (All Urban)",
    "UNRATE": "Unemployment Rate",
    "FEDFUNDS": "Federal Funds Effective Rate",
    "DGS10": "10-Year Treasury Yield",
    "UMCSENT": "University of Michigan Consumer Sentiment",
    "T10YIE": "10-Year Breakeven Inflation Rate",
    "VIXCLS": "CBOE Volatility Index (VIX)",
}


class FredCollector(BaseCollector):
    name = "fred"
    max_requests_per_minute = 120  # FRED is generous with rate limits

    def __init__(self):
        super().__init__()
        self.base_url = "https://api.stlouisfed.org/fred"
        self.api_key = settings.FRED_API_KEY

    # ── Public API ────────────────────────────────────────────────────

    async def collect(self, **kwargs) -> dict[str, Any]:
        """Collect latest values for all tracked economic indicators."""
        db_session: AsyncSession = kwargs["db_session"]
        total_inserted = 0

        async with self._build_client() as client:
            for series_id, series_name in FRED_SERIES.items():
                try:
                    observations = await self._fetch_series(client, series_id)
                    inserted = await self._store_observations(
                        db_session, series_id, series_name, observations
                    )
                    total_inserted += inserted
                    if inserted:
                        self.logger.info(
                            "Stored %d observations for %s", inserted, series_id
                        )
                except Exception as e:
                    self.logger.error("Failed to collect %s: %s", series_id, e)

        return {
            "status": "ok",
            "series_count": len(FRED_SERIES),
            "observations_inserted": total_inserted,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    async def _fetch_series(
        self, client, series_id: str, limit: int = 10
    ) -> list[dict]:
        """Fetch most recent observations for a FRED series."""
        resp = await self._request_with_retry(
            client, "GET",
            f"{self.base_url}/series/observations",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
        )
        data = resp.json()
        return data.get("observations", [])

    async def _store_observations(
        self,
        session: AsyncSession,
        series_id: str,
        series_name: str,
        observations: list[dict],
    ) -> int:
        """Insert observations, deduplicating by (indicator_code, date)."""
        rows = []
        for obs in observations:
            value_str = obs.get("value", ".")
            if value_str == ".":  # FRED uses "." for missing values
                continue
            try:
                value = float(value_str)
            except (ValueError, TypeError):
                continue
            date_str = obs.get("date", "")
            if not date_str:
                continue
            rows.append({
                "indicator_code": series_id,
                "name": series_name,
                "value": value,
                "date": datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                ),
                "source": "FRED",
            })

        if not rows:
            return 0

        stmt = (
            pg_insert(EconomicIndicator)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["indicator_code", "date"]
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount  # type: ignore[return-value]
