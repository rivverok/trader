"""Celery task for RL model inference — proposes trades in trading mode."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

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


@celery_app.task(name="run_rl_inference", bind=True, max_retries=1)
def run_rl_inference_task(self, force: bool = False) -> dict[str, Any]:
    """Assemble current state -> RL agent predict -> map actions -> risk check -> propose trades.

    Runs in trading mode only. Requires an active RL model to be loaded.
    """
    from app.tasks.task_status import is_system_paused, get_system_mode, update_task_status

    if not force and is_system_paused():
        return {"status": "system_paused"}

    if not force and get_system_mode() != "trading":
        return {"status": "skipped", "reason": "not in trading mode"}

    from app.engine.rl_agent import rl_agent

    if not rl_agent.is_loaded:
        return {"status": "skipped", "reason": "no RL model loaded"}

    async def _run() -> dict[str, Any]:
        async with async_session() as db:
            return await _run_inference(db)

    result = _run_async(_run())

    update_task_status("run_rl_inference", result)
    logger.info("RL inference complete: %s", result)
    return result


async def _run_inference(db) -> dict[str, Any]:
    """Core RL inference loop.

    Steps:
      1. Assemble state vector from latest data
      2. Run rl_agent.predict(state)
      3. Map discrete actions to trade proposals
      4. Risk check each trade
      5. Create ProposedTrade records

    Currently raises NotImplementedError — will be completed once an RL model
    is trained and the state vector assembly is validated with real data.
    """
    # TODO: Phase 3+ — implement after first model is trained
    #
    # 1. Get watchlist stocks
    # 2. For each stock, assemble feature vector matching training spec
    # 3. Stack into state matrix
    # 4. rl_agent.predict(state_matrix) -> action array
    # 5. Map actions: 0=strong_sell, 1=sell, 2=hold, 3=buy, 4=strong_buy
    # 6. For non-hold actions, calculate position size
    # 7. Risk check via check_trade_allowed()
    # 8. Create ProposedTrade records
    # 9. Return summary

    raise NotImplementedError(
        "RL inference not yet implemented — train a model first, "
        "then implement state vector assembly matching the training spec."
    )
