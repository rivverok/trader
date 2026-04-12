"""Celery task for capturing RL state snapshots."""

import asyncio
import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    from app.database import engine
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="capture_state_snapshot", bind=True, max_retries=2)
def capture_state_snapshot(self, snapshot_type: str = "daily_close", force: bool = False):
    """Capture a full RL state snapshot from all data sources.

    Runs in both data_collection and trading modes.
    Skipped when system_paused is True.
    """
    from app.tasks.task_status import is_system_paused, update_task_status

    if not force and is_system_paused():
        return {"status": "system_paused"}

    try:
        from app.engine.state_snapshots import capture_snapshot

        async def _capture():
            async with async_session() as db:
                snapshot = await capture_snapshot(
                    db, snapshot_type=snapshot_type
                )
                if snapshot:
                    return {
                        "status": "ok",
                        "snapshot_id": snapshot.id,
                        "timestamp": snapshot.timestamp.isoformat(),
                        "snapshot_type": snapshot.snapshot_type,
                    }
                return {"status": "skipped", "reason": "no watchlist stocks or data"}

        result = _run_async(_capture())
        update_task_status("capture_state_snapshot", result)
        logger.info("capture_state_snapshot: %s", result)
        return result

    except Exception as exc:
        from app.tasks.task_status import update_task_status
        update_task_status("capture_state_snapshot", {"status": "error", "error": str(exc)})
        logger.error("capture_state_snapshot failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
