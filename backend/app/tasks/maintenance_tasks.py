from app.celery_app import celery_app


@celery_app.task(name="health_check_task")
def health_check_task():
    """Simple task to verify Celery workers are running."""
    return {"status": "ok", "worker": "alive"}
