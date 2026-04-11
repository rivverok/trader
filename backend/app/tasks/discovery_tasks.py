"""Celery tasks for AI-driven stock discovery."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)

_discovery_status: dict[str, Any] = {
    "last_run": None,
    "last_result": {},
}


def get_discovery_status() -> dict[str, Any]:
    return dict(_discovery_status)


def _run_async(coro):
    from app.database import engine
    # Dispose stale connection pool from parent process / previous event loop
    # so the new loop gets fresh connections.
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="discover_stocks", bind=True, max_retries=1)
def discover_stocks(self, force=False) -> dict:
    """Run the AI stock discovery engine to find and curate watchlist stocks.

    Scheduled to run Tue/Thu at 7:00 AM ET (before market open).
    Can also be triggered manually.
    """
    from app.tasks.task_status import is_system_paused
    if not force and is_system_paused():
        return {"status": "system_paused"}
    logger.info("Starting stock discovery cycle")

    async def _run() -> dict:
        from app.engine.stock_discovery import run_stock_discovery

        async with async_session() as db:
            return await run_stock_discovery(db)

    try:
        result = _run_async(_run())
        from app.tasks.task_status import update_task_status
        update_task_status("discover_stocks", result)
        _discovery_status["last_run"] = datetime.now(timezone.utc).isoformat()
        _discovery_status["last_result"] = result
        logger.info("Stock discovery complete: %s", result)
        return result
    except Exception as exc:
        from app.tasks.task_status import update_task_status
        update_task_status("discover_stocks", {"status": "error", "error": str(exc)})
        _discovery_status["last_run"] = datetime.now(timezone.utc).isoformat()
        _discovery_status["last_result"] = {"status": "error", "error": str(exc)}
        logger.error("Stock discovery failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)
