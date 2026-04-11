"""Dynamic Celery Beat scheduler that auto-reloads when schedule_overrides.json changes.

Use instead of the default PersistentScheduler:
    celery -A app.celery_app beat --scheduler=app.dynamic_scheduler.DynamicScheduler
"""

import logging
import os
from pathlib import Path

from celery.beat import PersistentScheduler

logger = logging.getLogger(__name__)

OVERRIDES_DIR = os.environ.get("SCHEDULE_OVERRIDES_DIR", "/app/data")
OVERRIDES_PATH = Path(OVERRIDES_DIR) / "schedule_overrides.json"


class DynamicScheduler(PersistentScheduler):
    """Checks schedule_overrides.json for changes on every tick (~10s).

    When the file is created, modified, or deleted, the beat schedule is
    rebuilt from defaults + overrides and hot-swapped into the running
    scheduler — no container restart needed.
    """

    # Check for file changes every 10 seconds instead of default 5 minutes
    max_interval = 10

    def __init__(self, *args, **kwargs):
        self._last_mtime: float = 0.0
        super().__init__(*args, **kwargs)
        self._snapshot_mtime()

    def _snapshot_mtime(self):
        try:
            self._last_mtime = OVERRIDES_PATH.stat().st_mtime
        except FileNotFoundError:
            self._last_mtime = 0.0

    def _file_changed(self) -> bool:
        try:
            current = OVERRIDES_PATH.stat().st_mtime
        except FileNotFoundError:
            current = 0.0
        return current != self._last_mtime

    def tick(self):
        try:
            changed = self._file_changed()
            if changed:
                logger.info("Schedule overrides changed — reloading beat schedule")
                self._reload_schedule()
                self._snapshot_mtime()
        except Exception:
            logger.exception("Error checking schedule overrides")
        return super().tick()

    def _reload_schedule(self):
        from app.celery_app import _build_beat_schedule

        new_schedule = _build_beat_schedule()
        self.app.conf.beat_schedule = new_schedule

        # Clear the internal schedule entries and re-setup from the new config
        self.update_schedule(self.app)

    def update_schedule(self, app):
        """Re-read app.conf.beat_schedule into the scheduler's internal data structures."""
        from celery.beat import ScheduleEntry

        new_conf = app.conf.beat_schedule or {}

        # Build new entries from the updated config
        new_entries = {}
        for name, entry_dict in new_conf.items():
            task = entry_dict.get("task", name)
            schedule = entry_dict.get("schedule")
            args = entry_dict.get("args", ())
            kwargs = entry_dict.get("kwargs", {})
            options = entry_dict.get("options", {})
            relative = entry_dict.get("relative", False)
            new_entries[name] = self.Entry(
                name=name,
                task=task,
                schedule=schedule,
                args=args,
                kwargs=kwargs,
                options=options,
                app=app,
            )

        # Remove entries that are no longer in the schedule
        removed = set(self.data.keys()) - set(new_entries.keys())
        for key in removed:
            logger.info("Removing scheduled task: %s", key)
            self.data.pop(key, None)

        # Add or update entries
        for key, entry in new_entries.items():
            if key not in self.data:
                logger.info("Adding scheduled task: %s", key)
            self.data[key] = entry

        self.merge_inplace(self.schedule)
