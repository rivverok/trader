"""API route for collection pipeline status and manual triggers."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.tasks.collection_tasks import (
    backfill_historical_prices,
    collect_daily_bars,
    collect_economic_data,
    collect_filings,
    collect_news,
    collect_prices,
    get_collection_status,
)

router = APIRouter(prefix="/api/collection", tags=["collection"])


class CollectionStatusResponse(BaseModel):
    tasks: dict


class TriggerResponse(BaseModel):
    task_id: str
    task_name: str


@router.get("/status", response_model=CollectionStatusResponse)
async def collection_status():
    """Get the status of all collection tasks (last run, results)."""
    return CollectionStatusResponse(tasks=get_collection_status())


@router.post("/trigger/{task_name}", response_model=TriggerResponse)
async def trigger_collection(task_name: str):
    """Manually trigger a collection task."""
    tasks = {
        "prices": collect_prices,
        "daily_bars": collect_daily_bars,
        "news": collect_news,
        "economic": collect_economic_data,
        "filings": collect_filings,
        "backfill": backfill_historical_prices,
    }

    task_fn = tasks.get(task_name)
    if task_fn is None:
        from fastapi import HTTPException
        raise HTTPException(
            404,
            f"Unknown task '{task_name}'. Available: {', '.join(tasks.keys())}",
        )

    result = task_fn.delay()
    return TriggerResponse(task_id=result.id, task_name=task_name)
