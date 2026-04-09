from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "trader",
    broker=settings.get_redis_url(),
    backend=settings.get_redis_url(),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="US/Eastern",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # ── Prices: every minute during market hours (Mon-Fri, 9:30-16:00 ET) ──
        "collect-prices": {
            "task": "collect_prices",
            "schedule": crontab(
                minute="*",
                hour="9-15",
                day_of_week="mon-fri",
            ),
        },
        # ── Daily bars: 5:00 PM ET (after market close) ──
        "collect-daily-bars": {
            "task": "collect_daily_bars",
            "schedule": crontab(minute=0, hour=17, day_of_week="mon-fri"),
        },
        # ── News: every 30 minutes ──
        "collect-news": {
            "task": "collect_news",
            "schedule": settings.COLLECT_NEWS_INTERVAL_SEC,
        },
        # ── Economic data: daily at 8:00 AM ET ──
        "collect-economic-data": {
            "task": "collect_economic_data",
            "schedule": crontab(minute=0, hour=8),
        },
        # ── SEC filings: every 6 hours ──
        "collect-filings": {
            "task": "collect_filings",
            "schedule": settings.COLLECT_FILINGS_INTERVAL_SEC,
        },
        # ── Analysis: news sentiment every 15 minutes ──
        "analyze-news-sentiment": {
            "task": "analyze_news_sentiment",
            "schedule": 900,
        },
        # ── Analysis: SEC filings every hour ──
        "analyze-filings": {
            "task": "analyze_filings",
            "schedule": 3600,
        },
        # ── Analysis: context synthesis every 2 hours ──
        "run-context-synthesis": {
            "task": "run_context_synthesis",
            "schedule": 7200,
        },
        # ── ML: generate signals every hour during market hours ──
        "generate-ml-signals": {
            "task": "generate_ml_signals",
            "schedule": crontab(minute=0, hour="9-16", day_of_week="mon-fri"),
        },
        # ── ML: retrain model weekly on Sunday at 2 AM ──
        "retrain-model": {
            "task": "retrain_model",
            "schedule": crontab(minute=0, hour=2, day_of_week="sun"),
        },
        # ── Decision cycle: every 30 min during market hours ──
        "run-decision-cycle": {
            "task": "run_decision_cycle",
            "schedule": crontab(minute="0,30", hour="9-16", day_of_week="mon-fri"),
        },
        # ── Execute approved trades: every 1 minute during market hours ──
        "execute-approved-trades": {
            "task": "execute_approved_trades",
            "schedule": crontab(minute="*", hour="9-16", day_of_week="mon-fri"),
        },
        # ── Auto-approve proposals: every 1 minute during market hours ──
        "auto-execute-proposals": {
            "task": "auto_execute_proposals",
            "schedule": crontab(minute="*", hour="9-16", day_of_week="mon-fri"),
        },
        # ── Sync portfolio from Alpaca: every 5 minutes during market hours ──
        "sync-portfolio": {
            "task": "sync_portfolio",
            "schedule": crontab(minute="*/5", hour="9-16", day_of_week="mon-fri"),
        },
        # ── Check stop-loss orders: every 1 minute during market hours ──
        "check-stop-loss-orders": {
            "task": "check_stop_loss_orders",
            "schedule": crontab(minute="*", hour="9-16", day_of_week="mon-fri"),
        },
        # ── AI Stock Discovery: Tue/Thu at 7:00 AM ET (before market open) ──
        "discover-stocks": {
            "task": "discover_stocks",
            "schedule": crontab(minute=0, hour=7, day_of_week="tue,thu"),
        },
    },
)

# Auto-discover tasks from app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])
