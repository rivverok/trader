"""Schedule override manager — read/write schedule_overrides.json.

Each task in the Celery beat schedule can be:
  - enabled/disabled
  - have its interval (seconds) or crontab overridden

The overrides file is a JSON dict keyed by the beat‐schedule key (e.g.
"collect-news"), with values like:
  {"enabled": false}
  {"enabled": true, "interval_seconds": 3600}
  {"enabled": true, "crontab": {"minute": "0", "hour": "9-16", "day_of_week": "mon-fri"}}

The file lives at /app/data/schedule_overrides.json inside the container
(mounted as a Docker volume so it persists across rebuilds).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OVERRIDES_DIR = os.environ.get("SCHEDULE_OVERRIDES_DIR", "/app/data")
OVERRIDES_PATH = Path(OVERRIDES_DIR) / "schedule_overrides.json"


def _ensure_dir():
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_overrides() -> dict[str, Any]:
    """Load the overrides file, returning {} if missing or corrupt."""
    try:
        if OVERRIDES_PATH.exists():
            return json.loads(OVERRIDES_PATH.read_text())
    except Exception as e:
        logger.warning("Failed to read schedule overrides: %s", e)
    return {}


def save_overrides(overrides: dict[str, Any]) -> None:
    """Atomically write the overrides file."""
    _ensure_dir()
    tmp = OVERRIDES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(overrides, indent=2))
    tmp.replace(OVERRIDES_PATH)


def get_task_override(task_key: str) -> dict[str, Any] | None:
    """Get the override for a single task, or None."""
    return load_overrides().get(task_key)


def set_task_override(task_key: str, override: dict[str, Any]) -> None:
    """Set the override for a single task and persist."""
    all_overrides = load_overrides()
    all_overrides[task_key] = override
    save_overrides(all_overrides)


def delete_task_override(task_key: str) -> None:
    """Remove override for a task (revert to default)."""
    all_overrides = load_overrides()
    all_overrides.pop(task_key, None)
    save_overrides(all_overrides)
