"""Shared task status tracker — stores last-run info in Redis so the API can read it."""

import json
import logging
from datetime import datetime, timezone

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None

# Map Celery task names → beat schedule keys
_TASK_TO_SCHEDULE_KEY = {
    "collect_prices": "collect-prices",
    "collect_daily_bars": "collect-daily-bars",
    "collect_news": "collect-news",
    "collect_economic_data": "collect-economic-data",
    "collect_filings": "collect-filings",
    "backfill_historical_prices": "backfill-prices",
    "analyze_news_sentiment": "analyze-news-sentiment",
    "analyze_filings": "analyze-filings",
    "run_context_synthesis": "run-context-synthesis",
    "generate_ml_signals": "generate-ml-signals",
    "retrain_model": "retrain-model",
    "run_backtest": "run-backtest",
    "run_rl_inference": "run-rl-inference",
    "execute_approved_trades": "execute-approved-trades",
    "sync_portfolio": "sync-portfolio",
    "check_stop_loss_orders": "check-stop-loss-orders",
    "discover_stocks": "discover-stocks",
    "check_model_staleness": "check-model-staleness",
}

REDIS_KEY_PREFIX = "task_status:"


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.get_redis_url(), decode_responses=True)
    return _redis


def update_task_status(task_name: str, result: dict):
    """Record a task run in Redis. Called from Celery tasks after completion."""
    try:
        r = _get_redis()
        key = f"{REDIS_KEY_PREFIX}{task_name}"

        # Increment run count
        r.hincrby(key, "total_run_count", 1)
        r.hset(key, "last_run", datetime.now(timezone.utc).isoformat())
        r.hset(key, "last_result", json.dumps(result, default=str))
    except Exception as e:
        logger.warning("Failed to update task status for %s: %s", task_name, e)


def get_all_task_status() -> dict[str, dict]:
    """Read all task statuses from Redis. Called from the API."""
    try:
        r = _get_redis()
        result = {}
        for task_name, schedule_key in _TASK_TO_SCHEDULE_KEY.items():
            key = f"{REDIS_KEY_PREFIX}{task_name}"
            data = r.hgetall(key)
            if data:
                result[schedule_key] = {
                    "last_run": data.get("last_run"),
                    "total_run_count": int(data.get("total_run_count", 0)),
                }
        return result
    except Exception as e:
        logger.warning("Failed to read task statuses: %s", e)
        return {}


def is_system_paused() -> bool:
    """Check if the system is paused by reading the DB flag via a quick query.

    Returns True if system_paused is set, meaning all scheduled tasks should skip.
    """
    try:
        import asyncio
        from app.database import async_session, engine
        from app.engine.risk_manager import get_risk_state

        async def _check():
            async with async_session() as db:
                state = await get_risk_state(db)
                return state.system_paused

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.dispose())
            return loop.run_until_complete(_check())
        finally:
            loop.close()
    except Exception as e:
        logger.warning("Failed to check system_paused: %s", e)
        return False


def get_system_mode() -> str:
    """Get the current system mode from the DB.

    Returns 'data_collection' or 'trading'.
    """
    try:
        import asyncio
        from app.database import async_session, engine
        from app.engine.risk_manager import get_risk_state

        async def _check():
            async with async_session() as db:
                state = await get_risk_state(db)
                return state.system_mode

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.dispose())
            return loop.run_until_complete(_check())
        finally:
            loop.close()
    except Exception as e:
        logger.warning("Failed to check system_mode: %s", e)
        return "data_collection"
