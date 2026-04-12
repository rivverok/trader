"""Celery tasks for the decision engine cycle.

The decision engine has been simplified — it now delegates to the RL inference
task in trading mode. This task is kept for backward compatibility but most
logic now lives in rl_tasks.py.
"""

import asyncio
import logging
from typing import Any

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)

_decision_status: dict[str, Any] = {
    "last_run": None,
    "last_result": {},
}


def get_decision_status() -> dict[str, Any]:
    return dict(_decision_status)


def _run_async(coro):
    from app.database import engine
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="run_decision_cycle", bind=True, max_retries=1)
def run_decision_cycle_task(self, force=False) -> dict:
    """Legacy decision cycle — delegates to RL agent.

    Kept for backward compatibility with existing Celery schedule.
    In trading mode, prefer run_rl_inference_task directly.
    """
    from datetime import datetime, timezone
    from app.tasks.task_status import is_system_paused, get_system_mode
    if not force and is_system_paused():
        return {"status": "system_paused"}
    if not force and get_system_mode() != "trading":
        return {"status": "skipped", "reason": "not in trading mode"}

    logger.info("Starting decision cycle (delegating to RL agent)")

    async def _run() -> dict:
        from app.engine.decision_engine import run_decision_cycle

        async with async_session() as db:
            return await run_decision_cycle(db)

    result = _run_async(_run())

    from app.tasks.task_status import update_task_status
    update_task_status("run_decision_cycle", result)
    _decision_status["last_run"] = datetime.now(timezone.utc).isoformat()
    _decision_status["last_result"] = result

    logger.info("Decision cycle complete: %s", result)
    return result
