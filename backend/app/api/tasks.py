"""Task Management API — list, inspect, cancel, and retry Celery tasks."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskInfo(BaseModel):
    task_id: str
    name: str | None = None
    status: str  # PENDING, STARTED, PROGRESS, SUCCESS, FAILURE, REVOKED, RETRY
    result: str | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    worker: str | None = None
    args: str | None = None
    kwargs: str | None = None
    progress: dict | None = None


class ActiveTask(BaseModel):
    task_id: str
    name: str
    status: str
    worker: str
    started_at: str | None = None
    args: str | None = None
    kwargs: str | None = None


class ScheduledTask(BaseModel):
    key: str  # beat schedule key, e.g. "collect-news"
    name: str
    schedule: str
    enabled: bool = True
    last_run: str | None = None
    total_run_count: int | None = None


class TaskListResponse(BaseModel):
    active: list[ActiveTask]
    reserved: list[ActiveTask]
    scheduled_periodic: list[ScheduledTask]


class TaskActionResponse(BaseModel):
    task_id: str
    action: str
    success: bool
    message: str


class DataSourceStatus(BaseModel):
    name: str
    rows: int
    latest: str | None = None
    detail: str | None = None


class DataStatusResponse(BaseModel):
    sources: list[DataSourceStatus]


@router.get("/", response_model=TaskListResponse)
async def list_tasks():
    """List all active, reserved (queued), and periodic tasks."""
    loop = asyncio.get_event_loop()

    # Run both inspector calls in parallel in a thread pool (each blocks up to 1.5s)
    async def _inspect_active():
        inspector = celery_app.control.inspect(timeout=1.5)
        return await loop.run_in_executor(None, inspector.active)

    async def _inspect_reserved():
        inspector = celery_app.control.inspect(timeout=1.5)
        return await loop.run_in_executor(None, inspector.reserved)

    active_raw_result, reserved_raw_result = await asyncio.gather(
        _inspect_active(), _inspect_reserved()
    )

    # Active tasks (currently executing)
    active_tasks = []
    active_raw = active_raw_result or {}
    for worker_name, tasks in active_raw.items():
        for t in tasks:
            active_tasks.append(ActiveTask(
                task_id=t.get("id", ""),
                name=t.get("name", "unknown"),
                status="STARTED",
                worker=worker_name,
                started_at=_format_timestamp(t.get("time_start")),
                args=str(t.get("args", "")),
                kwargs=str(t.get("kwargs", "")),
            ))

    # Reserved tasks (received by worker but not yet started)
    reserved_tasks = []
    reserved_raw = reserved_raw_result or {}
    for worker_name, tasks in reserved_raw.items():
        for t in tasks:
            reserved_tasks.append(ActiveTask(
                task_id=t.get("id", ""),
                name=t.get("name", "unknown"),
                status="QUEUED",
                worker=worker_name,
                args=str(t.get("args", "")),
                kwargs=str(t.get("kwargs", "")),
            ))

    # Beat schedule — show ALL tasks (including disabled) so UI can toggle them
    from app.celery_app import _build_beat_schedule
    from app.schedule_overrides import load_overrides

    periodic_tasks = []
    # Re-import defaults by calling with no overrides
    # We need the full default list, so import _build_beat_schedule internals
    overrides = load_overrides()

    # Get the currently active schedule (enabled tasks only)
    active_schedule = celery_app.conf.beat_schedule or {}

    # We also need to show disabled tasks — rebuild from defaults
    from app.celery_app import _get_default_schedule
    all_defaults = _get_default_schedule()

    for task_key, task_conf in all_defaults.items():
        ovr = overrides.get(task_key, {})
        enabled = ovr.get("enabled", True) is not False

        # Use overridden schedule for display if present
        if task_key in active_schedule:
            schedule = active_schedule[task_key].get("schedule", "")
        elif "interval_seconds" in ovr:
            schedule = ovr["interval_seconds"]
        else:
            schedule = task_conf.get("schedule", "")

        periodic_tasks.append(ScheduledTask(
            key=task_key,
            name=task_conf.get("task", task_key),
            schedule=str(schedule),
            enabled=enabled,
        ))

    return TaskListResponse(
        active=active_tasks,
        reserved=reserved_tasks,
        scheduled_periodic=periodic_tasks,
    )


@router.get("/data-status", response_model=DataStatusResponse)
async def data_status(db: AsyncSession = Depends(get_db)):
    """Return row counts and latest dates for all data sources."""
    from app.models.stock import Stock
    from app.models.price import Price
    from app.models.economic import EconomicIndicator
    from app.models.news import NewsArticle
    from app.models.sec_filing import SecFiling
    from app.models.analysis import NewsAnalysis, FilingAnalysis, ContextSynthesis
    from app.models.signal import MLSignal

    sources: list[DataSourceStatus] = []

    # Watchlist stocks
    r = await db.execute(
        select(func.count()).select_from(Stock).where(Stock.on_watchlist.is_(True))
    )
    watchlist_count = r.scalar() or 0
    r = await db.execute(select(func.count()).select_from(Stock))
    total_stocks = r.scalar() or 0
    sources.append(DataSourceStatus(
        name="Watchlist Stocks",
        rows=watchlist_count,
        detail=f"{total_stocks} total stocks tracked",
    ))

    # Prices
    r = await db.execute(select(func.count(), func.max(Price.timestamp)).select_from(Price))
    row = r.one()
    sources.append(DataSourceStatus(
        name="Price Bars",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
    ))

    # Economic indicators
    r = await db.execute(
        select(
            func.count(),
            func.max(EconomicIndicator.date),
            func.count(func.distinct(EconomicIndicator.indicator_code)),
        ).select_from(EconomicIndicator)
    )
    row = r.one()
    sources.append(DataSourceStatus(
        name="Economic Indicators",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
        detail=f"{row[2]} series (GDP, CPI, rates, VIX, etc.)",
    ))

    # News articles
    r = await db.execute(
        select(
            func.count(),
            func.max(NewsArticle.published_at),
            func.count().filter(NewsArticle.analyzed.is_(True)),
        ).select_from(NewsArticle)
    )
    row = r.one()
    total_news = row[0] or 0
    analyzed_news = row[2] or 0
    sources.append(DataSourceStatus(
        name="News Articles",
        rows=total_news,
        latest=row[1].isoformat() if row[1] else None,
        detail=f"{analyzed_news}/{total_news} analyzed",
    ))

    # SEC filings
    r = await db.execute(
        select(
            func.count(),
            func.max(SecFiling.filed_date),
            func.count().filter(SecFiling.analyzed.is_(True)),
        ).select_from(SecFiling)
    )
    row = r.one()
    total_filings = row[0] or 0
    analyzed_filings = row[2] or 0
    sources.append(DataSourceStatus(
        name="SEC Filings",
        rows=total_filings,
        latest=row[1].isoformat() if row[1] else None,
        detail=f"{analyzed_filings}/{total_filings} analyzed",
    ))

    # News analyses
    r = await db.execute(select(func.count(), func.max(NewsAnalysis.created_at)).select_from(NewsAnalysis))
    row = r.one()
    sources.append(DataSourceStatus(
        name="News Analyses",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
    ))

    # Filing analyses
    r = await db.execute(select(func.count(), func.max(FilingAnalysis.created_at)).select_from(FilingAnalysis))
    row = r.one()
    sources.append(DataSourceStatus(
        name="Filing Analyses",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
    ))

    # Context syntheses
    r = await db.execute(select(func.count(), func.max(ContextSynthesis.created_at)).select_from(ContextSynthesis))
    row = r.one()
    sources.append(DataSourceStatus(
        name="Context Syntheses",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
    ))

    # ML signals
    r = await db.execute(select(func.count(), func.max(MLSignal.created_at)).select_from(MLSignal))
    row = r.one()
    sources.append(DataSourceStatus(
        name="ML Signals",
        rows=row[0] or 0,
        latest=row[1].isoformat() if row[1] else None,
    ))

    return DataStatusResponse(sources=sources)


@router.get("/{task_id}", response_model=TaskInfo)
async def get_task_status(task_id: str):
    """Get the status and result of a specific task by ID."""
    result = AsyncResult(task_id, app=celery_app)

    error = None
    result_str = None
    progress = None
    if result.state == "FAILURE":
        error = str(result.result) if result.result else "Unknown error"
    elif result.state == "SUCCESS":
        result_str = str(result.result)[:2000] if result.result else None
    elif result.state == "PROGRESS":
        progress = result.info if isinstance(result.info, dict) else None

    info = result.info or {}
    started_at = None
    if isinstance(info, dict):
        started_at = info.get("started_at")

    return TaskInfo(
        task_id=task_id,
        name=result.name,
        status=result.state,
        result=result_str,
        error=error,
        started_at=started_at,
        worker=info.get("hostname") if isinstance(info, dict) else None,
        progress=progress,
    )


@router.post("/{task_id}/cancel", response_model=TaskActionResponse)
async def cancel_task(task_id: str):
    """Cancel/revoke a queued or running task."""
    try:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        return TaskActionResponse(
            task_id=task_id,
            action="cancel",
            success=True,
            message="Task cancellation signal sent",
        )
    except Exception as e:
        return TaskActionResponse(
            task_id=task_id,
            action="cancel",
            success=False,
            message=str(e),
        )


@router.post("/{task_id}/retry", response_model=TaskActionResponse)
async def retry_task(task_id: str):
    """Retry a failed task by looking up its name and re-dispatching."""
    result = AsyncResult(task_id, app=celery_app)

    if not result.name:
        return TaskActionResponse(
            task_id=task_id,
            action="retry",
            success=False,
            message="Cannot determine task name — task may have expired from result backend",
        )

    try:
        # Re-send the same task
        new_result = celery_app.send_task(result.name)
        return TaskActionResponse(
            task_id=new_result.id,
            action="retry",
            success=True,
            message=f"Re-queued as {new_result.id}",
        )
    except Exception as e:
        return TaskActionResponse(
            task_id=task_id,
            action="retry",
            success=False,
            message=str(e),
        )


def _format_timestamp(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return None


# ── Schedule Override Endpoints ──────────────────────────────────────────


class ScheduleOverrideRequest(BaseModel):
    enabled: bool = True
    interval_seconds: int | None = None  # For simple interval schedules
    crontab: dict[str, str] | None = None  # e.g. {"minute": "0", "hour": "9-16", "day_of_week": "mon-fri"}


class ScheduleOverrideResponse(BaseModel):
    key: str
    enabled: bool
    schedule: str
    message: str


@router.put("/schedules/{task_key}", response_model=ScheduleOverrideResponse)
async def update_schedule(task_key: str, body: ScheduleOverrideRequest):
    """Update the schedule override for a task. Requires scheduler restart to take effect."""
    from app.celery_app import _get_default_schedule
    from app.schedule_overrides import set_task_override
    from celery.schedules import crontab as make_crontab

    defaults = _get_default_schedule()
    if task_key not in defaults:
        raise HTTPException(404, f"Unknown task key: {task_key}")

    override: dict[str, Any] = {"enabled": body.enabled}
    if body.interval_seconds is not None:
        if body.interval_seconds < 10:
            raise HTTPException(400, "Interval must be at least 10 seconds")
        override["interval_seconds"] = body.interval_seconds
    elif body.crontab is not None:
        allowed_keys = {"minute", "hour", "day_of_week", "day_of_month", "month_of_year"}
        if not body.crontab.keys() <= allowed_keys:
            raise HTTPException(400, f"Invalid crontab keys. Allowed: {allowed_keys}")
        # Validate by constructing a crontab
        try:
            make_crontab(**body.crontab)
        except Exception as e:
            raise HTTPException(400, f"Invalid crontab: {e}")
        override["crontab"] = body.crontab

    set_task_override(task_key, override)

    # Compute display schedule
    if body.interval_seconds is not None:
        display = str(body.interval_seconds)
    elif body.crontab is not None:
        display = str(make_crontab(**body.crontab))
    else:
        display = str(defaults[task_key]["schedule"])

    return ScheduleOverrideResponse(
        key=task_key,
        enabled=body.enabled,
        schedule=display,
        message="Schedule updated — applied automatically within a few seconds.",
    )


@router.delete("/schedules/{task_key}", response_model=ScheduleOverrideResponse)
async def reset_schedule(task_key: str):
    """Remove override for a task and revert to default schedule."""
    from app.celery_app import _get_default_schedule
    from app.schedule_overrides import delete_task_override

    defaults = _get_default_schedule()
    if task_key not in defaults:
        raise HTTPException(404, f"Unknown task key: {task_key}")

    delete_task_override(task_key)

    return ScheduleOverrideResponse(
        key=task_key,
        enabled=True,
        schedule=str(defaults[task_key]["schedule"]),
        message="Reset to default — applied automatically within a few seconds.",
    )
