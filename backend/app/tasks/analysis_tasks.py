"""Celery tasks for Claude-powered analysis — scheduled by Beat."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)

# ── Analysis status tracking (in-memory, reset on restart) ───────────
_analysis_status: dict[str, dict[str, Any]] = {}


def _update_status(task_name: str, result: dict):
    from app.tasks.task_status import update_task_status
    update_task_status(task_name, result)
    _analysis_status[task_name] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_result": result,
    }


def get_analysis_status() -> dict[str, dict[str, Any]]:
    return dict(_analysis_status)


def _run_async(coro):
    from app.database import engine
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── News sentiment analysis ──────────────────────────────────────────

@celery_app.task(name="analyze_news_sentiment", bind=True, max_retries=1)
def analyze_news_sentiment(self, force=False):
    """Analyze pending news articles using Claude Haiku."""
    from app.tasks.task_status import is_system_paused
    if not force and is_system_paused():
        return {"status": "system_paused"}
    try:
        from app.analysis.sentiment import analyze_pending_news

        async def _analyze():
            async with async_session() as session:
                return await analyze_pending_news(db_session=session)

        result = _run_async(_analyze())
        _update_status("analyze_news_sentiment", result)
        logger.info("analyze_news_sentiment: %s", result)
        return result
    except Exception as exc:
        _update_status("analyze_news_sentiment", {"status": "error", "error": str(exc)})
        logger.error("analyze_news_sentiment failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ── SEC filing analysis ──────────────────────────────────────────────

@celery_app.task(name="analyze_filings", bind=True, max_retries=1)
def analyze_filings(self, force=False):
    """Analyze pending SEC filings using Claude Sonnet."""
    from app.tasks.task_status import is_system_paused
    if not force and is_system_paused():
        return {"status": "system_paused"}
    try:
        from app.analysis.filings import analyze_pending_filings

        async def _analyze():
            async with async_session() as session:
                return await analyze_pending_filings(db_session=session)

        result = _run_async(_analyze())
        _update_status("analyze_filings", result)
        logger.info("analyze_filings: %s", result)
        return result
    except Exception as exc:
        _update_status("analyze_filings", {"status": "error", "error": str(exc)})
        logger.error("analyze_filings failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ── Context synthesis ────────────────────────────────────────────────

@celery_app.task(name="run_context_synthesis", bind=True, max_retries=1)
def run_context_synthesis(self, force=False):
    """Run holistic context synthesis for all watchlist stocks using Claude Sonnet."""
    from app.tasks.task_status import is_system_paused
    if not force and is_system_paused():
        return {"status": "system_paused"}
    try:
        from app.analysis.context_synthesis import run_context_synthesis as _synth

        async def _analyze():
            async with async_session() as session:
                return await _synth(db_session=session)

        result = _run_async(_analyze())
        _update_status("run_context_synthesis", result)
        logger.info("run_context_synthesis: %s", result)
        return result
    except Exception as exc:
        _update_status("run_context_synthesis", {"status": "error", "error": str(exc)})
        logger.error("run_context_synthesis failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)
