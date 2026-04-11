from app.celery_app import celery_app

# Explicitly import all task modules so Celery registers them
from app.tasks import collection_tasks  # noqa: F401
from app.tasks import analysis_tasks  # noqa: F401
from app.tasks import decision_tasks  # noqa: F401
from app.tasks import execution_tasks  # noqa: F401
from app.tasks import ml_tasks  # noqa: F401
from app.tasks import discovery_tasks  # noqa: F401
from app.tasks import maintenance_tasks  # noqa: F401

__all__ = ["celery_app"]
