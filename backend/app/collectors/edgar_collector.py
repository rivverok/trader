"""SEC EDGAR collector — 10-K, 10-Q, 8-K filings via EDGAR full-text search."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import BaseCollector
from app.config import settings
from app.models.sec_filing import SecFiling
from app.models.stock import Stock

# EDGAR EFTS (full-text search) API
EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
# EDGAR company filings API
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
# Filing types we care about
FILING_TYPES = ["10-K", "10-Q", "8-K"]


class EdgarCollector(BaseCollector):
    name = "edgar"
    max_requests_per_minute = 120  # SEC allows 10 req/sec; 2/sec avg is very safe

    def __init__(self):
        super().__init__()
        self.user_agent = settings.SEC_EDGAR_USER_AGENT or "AI Trader app@example.com"

    # ── Public API ────────────────────────────────────────────────────

    async def collect(self, **kwargs) -> dict[str, Any]:
        """Collect recent SEC filings for all watchlist stocks."""
        db_session: AsyncSession = kwargs["db_session"]
        stocks = await self._get_watchlist_stocks(db_session)
        if not stocks:
            return {"status": "skip", "reason": "no watchlist stocks"}

        total_inserted = 0
        total_downloaded = 0
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        async with self._build_client(headers=headers) as client:
            for stock in stocks:
                try:
                    filings = await self._fetch_filings(client, stock.symbol)
                    inserted = await self._store_filings(
                        db_session, filings, stock.id
                    )
                    total_inserted += inserted
                    if inserted:
                        self.logger.info(
                            "Stored %d filings for %s", inserted, stock.symbol
                        )
                except Exception as e:
                    self.logger.error(
                        "Failed to collect filings for %s: %s", stock.symbol, e
                    )

            # Download content for filings that have a URL but no content yet
            downloaded = await self._download_missing_content(
                client, db_session
            )
            total_downloaded += downloaded

        return {
            "status": "ok",
            "symbols": len(stocks),
            "filings_inserted": total_inserted,
            "content_downloaded": total_downloaded,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    async def _get_watchlist_stocks(self, session: AsyncSession) -> list[Stock]:
        result = await session.execute(
            select(Stock).where(Stock.on_watchlist.is_(True))
        )
        return list(result.scalars().all())

    async def _fetch_filings(self, client, ticker: str) -> list[dict]:
        """Search EDGAR EFTS for recent filings by ticker."""
        filings_found: list[dict] = []

        for filing_type in FILING_TYPES:
            resp = await self._request_with_retry(
                client, "GET",
                "https://efts.sec.gov/LATEST/search-index",
                params={
                    "q": f'"{ticker}"',
                    "dateRange": "custom",
                    "startdt": "2020-01-01",
                    "enddt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "forms": filing_type,
                },
            )
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            for hit in hits[:5]:  # Limit to 5 most recent per type
                source = hit.get("_source", {})
                # Build EDGAR filing URL from CIK and accession number
                accession_raw = source.get("adsh", "")
                filed_date_str = source.get("file_date", "")
                ciks = source.get("ciks", [])

                if not accession_raw or not filed_date_str or not ciks:
                    continue

                cik = ciks[0]  # e.g. "0000050863"
                # Clean accession number for URL path (remove dashes)
                accession_clean = accession_raw.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{accession_clean}/{accession_raw}-index.htm"
                )

                try:
                    filed_date = datetime.strptime(
                        filed_date_str, "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                filings_found.append({
                    "filing_type": filing_type,
                    "filed_date": filed_date,
                    "accession_number": accession_raw[:30],
                    "url": filing_url[:500],
                })

        return filings_found

    async def _fetch_filing_content(self, client, url: str) -> str | None:
        """Download the raw filing text. Returns None on failure.
        
        The URL points to the filing index page (-index.htm). We convert it
        to the full submission text file (.txt) for easy parsing.
        """
        try:
            # Convert index URL to full submission text URL
            # e.g. .../0000050863-25-000009-index.htm -> .../0000050863-25-000009.txt
            text_url = url.replace("-index.htm", ".txt")
            resp = await self._request_with_retry(client, "GET", text_url)
            text = resp.text
            if not text:
                return None
            # Strip SGML headers/tags for cleaner content, keep just text
            # Truncate very large filings to ~200KB to manage DB size and Claude token limits
            cleaned = text[:200_000]
            return cleaned
        except Exception as e:
            self.logger.warning("Could not download filing content from %s: %s", url, e)
            return None

    async def _download_missing_content(
        self, client, session: AsyncSession
    ) -> int:
        """Download raw content for filings that have a URL but no content."""
        from sqlalchemy import update

        result = await session.execute(
            select(SecFiling)
            .where(SecFiling.raw_content.is_(None))
            .where(SecFiling.url.isnot(None))
            .order_by(SecFiling.filed_date.desc())
            .limit(250)  # Process a large batch; rate limiter handles pacing
        )
        filings = list(result.scalars().all())
        if not filings:
            return 0

        downloaded = 0
        for filing in filings:
            content = await self._fetch_filing_content(client, filing.url)
            if content and len(content) > 100:
                await session.execute(
                    update(SecFiling)
                    .where(SecFiling.id == filing.id)
                    .values(raw_content=content)
                )
                downloaded += 1
                self.logger.info(
                    "Downloaded content for filing %s (%d chars)",
                    filing.accession_number, len(content),
                )

        if downloaded:
            await session.commit()
        return downloaded

    async def _store_filings(
        self, session: AsyncSession, filings: list[dict], stock_id: int
    ) -> int:
        """Insert filings, deduplicating by accession_number."""
        if not filings:
            return 0

        rows = []
        for filing in filings:
            rows.append({
                "stock_id": stock_id,
                "filing_type": filing["filing_type"],
                "filed_date": filing["filed_date"],
                "accession_number": filing["accession_number"],
                "url": filing["url"],
                "raw_content": None,  # Content fetched lazily by analysis stage
                "analyzed": False,
            })

        stmt = (
            pg_insert(SecFiling)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["accession_number"])
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount  # type: ignore[return-value]
