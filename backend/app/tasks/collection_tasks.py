"""Celery tasks for data collection — scheduled by Beat."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)

# ── Collection status tracking (in-memory, reset on restart) ─────────
_collection_status: dict[str, dict[str, Any]] = {}


def _update_status(task_name: str, result: dict):
    _collection_status[task_name] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_result": result,
    }


def get_collection_status() -> dict[str, dict[str, Any]]:
    return dict(_collection_status)


# ── Helper: run async collector in sync Celery task ──────────────────

def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Price collection ─────────────────────────────────────────────────

@celery_app.task(name="collect_prices", bind=True, max_retries=2)
def collect_prices(self):
    """Collect latest 1-min bars for watchlist stocks."""
    try:
        from app.collectors.alpaca_collector import AlpacaCollector

        async def _collect():
            collector = AlpacaCollector()
            async with async_session() as session:
                return await collector.collect(db_session=session)

        result = _run_async(_collect())
        _update_status("collect_prices", result)
        logger.info("collect_prices: %s", result)
        return result
    except Exception as exc:
        _update_status("collect_prices", {"status": "error", "error": str(exc)})
        logger.error("collect_prices failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="collect_daily_bars", bind=True, max_retries=2)
def collect_daily_bars(self):
    """Collect end-of-day bars after market close."""
    try:
        from app.collectors.alpaca_collector import AlpacaCollector

        async def _collect():
            collector = AlpacaCollector()
            async with async_session() as session:
                return await collector.collect_daily_bars(db_session=session)

        result = _run_async(_collect())
        _update_status("collect_daily_bars", result)
        logger.info("collect_daily_bars: %s", result)
        return result
    except Exception as exc:
        _update_status("collect_daily_bars", {"status": "error", "error": str(exc)})
        logger.error("collect_daily_bars failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ── News collection ──────────────────────────────────────────────────

@celery_app.task(name="collect_news", bind=True, max_retries=2)
def collect_news(self):
    """Collect news articles for watchlist stocks from Finnhub."""
    try:
        from app.collectors.finnhub_collector import FinnhubCollector

        async def _collect():
            collector = FinnhubCollector()
            async with async_session() as session:
                return await collector.collect(db_session=session)

        result = _run_async(_collect())
        _update_status("collect_news", result)
        logger.info("collect_news: %s", result)
        return result
    except Exception as exc:
        _update_status("collect_news", {"status": "error", "error": str(exc)})
        logger.error("collect_news failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ── Economic data ────────────────────────────────────────────────────

@celery_app.task(name="collect_economic_data", bind=True, max_retries=2)
def collect_economic_data(self):
    """Collect economic indicators from FRED."""
    try:
        from app.collectors.fred_collector import FredCollector

        async def _collect():
            collector = FredCollector()
            async with async_session() as session:
                return await collector.collect(db_session=session)

        result = _run_async(_collect())
        _update_status("collect_economic_data", result)
        logger.info("collect_economic_data: %s", result)
        return result
    except Exception as exc:
        _update_status("collect_economic_data", {"status": "error", "error": str(exc)})
        logger.error("collect_economic_data failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ── SEC filings ──────────────────────────────────────────────────────

@celery_app.task(name="collect_filings", bind=True, max_retries=2)
def collect_filings(self):
    """Collect SEC filings for watchlist stocks from EDGAR."""
    try:
        from app.collectors.edgar_collector import EdgarCollector

        async def _collect():
            collector = EdgarCollector()
            async with async_session() as session:
                return await collector.collect(db_session=session)

        result = _run_async(_collect())
        _update_status("collect_filings", result)
        logger.info("collect_filings: %s", result)
        return result
    except Exception as exc:
        _update_status("collect_filings", {"status": "error", "error": str(exc)})
        logger.error("collect_filings failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ── Backfill (one-time manual trigger) ───────────────────────────────

@celery_app.task(name="backfill_historical_prices")
def backfill_historical_prices(years: int = 5):
    """Backfill historical daily bars. Run manually via CLI or API."""
    from app.collectors.alpaca_collector import AlpacaCollector

    async def _backfill():
        collector = AlpacaCollector()
        async with async_session() as session:
            return await collector.backfill_historical(db_session=session, years=years)

    result = _run_async(_backfill())
    _update_status("backfill_historical_prices", result)
    logger.info("backfill_historical_prices: %s", result)
    return result
