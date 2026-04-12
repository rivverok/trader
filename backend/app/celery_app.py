from celery import Celery
from celery.schedules import crontab
from app.config import settings
from app.schedule_overrides import load_overrides

celery_app = Celery(
    "trader",
    broker=settings.get_redis_url(),
    backend=settings.get_redis_url(),
)


def _get_default_schedule() -> dict:
    """Return the built-in default beat schedule (no overrides applied)."""
    return {
        "collect-prices": {
            "task": "collect_prices",
            "schedule": crontab(minute="*", hour="9-15", day_of_week="mon-fri"),
        },
        "collect-daily-bars": {
            "task": "collect_daily_bars",
            "schedule": crontab(minute=0, hour=17, day_of_week="mon-fri"),
        },
        "collect-news": {
            "task": "collect_news",
            "schedule": settings.COLLECT_NEWS_INTERVAL_SEC,
        },
        "collect-economic-data": {
            "task": "collect_economic_data",
            "schedule": crontab(minute=0, hour=8),
        },
        "collect-filings": {
            "task": "collect_filings",
            "schedule": settings.COLLECT_FILINGS_INTERVAL_SEC,
        },
        "analyze-news-sentiment": {
            "task": "analyze_news_sentiment",
            "schedule": settings.ANALYZE_NEWS_INTERVAL_SEC,
        },
        "analyze-filings": {
            "task": "analyze_filings",
            "schedule": settings.ANALYZE_FILINGS_INTERVAL_SEC,
        },
        "run-context-synthesis": {
            "task": "run_context_synthesis",
            "schedule": settings.CONTEXT_SYNTHESIS_INTERVAL_SEC,
        },
        "generate-ml-signals": {
            "task": "generate_ml_signals",
            "schedule": crontab(minute=0, hour="7-20", day_of_week="mon-fri"),
        },
        "retrain-model": {
            "task": "retrain_model",
            "schedule": crontab(minute=0, hour=2, day_of_week="sun"),
        },
        # ── Trading-mode tasks (mode-gated, skip in data_collection) ──
        "run-rl-inference": {
            "task": "run_rl_inference",
            "schedule": crontab(minute="0,30", hour="9-16", day_of_week="mon-fri"),
        },
        "execute-approved-trades": {
            "task": "execute_approved_trades",
            "schedule": crontab(minute="*/5", hour="9-16", day_of_week="mon-fri"),
        },
        "sync-portfolio": {
            "task": "sync_portfolio",
            "schedule": crontab(minute="*/5", hour="9-16", day_of_week="mon-fri"),
        },
        "check-stop-loss-orders": {
            "task": "check_stop_loss_orders",
            "schedule": crontab(minute="*/5", hour="9-16", day_of_week="mon-fri"),
        },
        "discover-stocks": {
            "task": "discover_stocks",
            "schedule": crontab(minute=0, hour=7, day_of_week="tue,thu"),
        },
        "check-model-staleness": {
            "task": "check_model_staleness",
            "schedule": crontab(minute=0, hour=8),
        },

    }


def _build_beat_schedule() -> dict:
    """Build beat schedule from defaults, applying any user overrides."""
    defaults = _get_default_schedule()

    # Apply user overrides
    overrides = load_overrides()
    schedule = {}
    for key, conf in defaults.items():
        ovr = overrides.get(key, {})
        # Skip disabled tasks
        if ovr.get("enabled") is False:
            continue
        # Override schedule if specified
        if "interval_seconds" in ovr:
            conf = {**conf, "schedule": ovr["interval_seconds"]}
        elif "crontab" in ovr:
            conf = {**conf, "schedule": crontab(**ovr["crontab"])}
        schedule[key] = conf

    # ── Always-on tasks (not affected by overrides or system pause) ───
    schedule["run-database-backup"] = {
        "task": "run_database_backup",
        "schedule": crontab(minute=0, hour=2),
    }

    return schedule

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="US/Eastern",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule=_build_beat_schedule(),
)

# Auto-discover tasks from app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])
