"""Celery task for automated database backups.

Runs daily via beat schedule. Does NOT check system_paused —
backups must always run regardless of trading pause state.
"""

import glob
import gzip
import logging
import os
import subprocess
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

RETAIN_DAYS = 30


def _write_status(status: str, message: str):
    """Write backup status to system_kv table (sync via psycopg2)."""
    import psycopg2

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dsn = (
        f"host={settings.POSTGRES_HOST} port={settings.POSTGRES_PORT} "
        f"dbname={settings.POSTGRES_DB} user={settings.POSTGRES_USER} "
        f"password={settings.POSTGRES_PASSWORD}"
    )
    try:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO system_kv (key, value, updated_at)
                    VALUES ('backup_last_status', %s, NOW()),
                           ('backup_last_time', %s, NOW()),
                           ('backup_last_message', %s, NOW())
                    ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (status, now, message),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to write backup status to DB: %s", exc)


def _prune_old_backups(backup_dir: str):
    """Remove backup files older than RETAIN_DAYS."""
    import time

    cutoff = time.time() - (RETAIN_DAYS * 86400)
    pattern = os.path.join(backup_dir, "trader_*.sql.gz")
    removed = 0
    for path in glob.glob(pattern):
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    if removed:
        logger.info("Pruned %d old backup(s)", removed)


@celery_app.task(name="run_database_backup", bind=True, max_retries=1)
def run_database_backup(self):
    """Dump PostgreSQL database to BACKUP_DIR.

    This task intentionally does NOT check is_system_paused() —
    backups always run regardless of trading state.
    """
    backup_dir = settings.BACKUP_DIR
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"trader_{timestamp}.sql.gz"
    filepath = os.path.join(backup_dir, filename)

    # Ensure backup directory exists
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except OSError:
        pass

    if not os.path.isdir(backup_dir) or not os.access(backup_dir, os.W_OK):
        msg = f"Backup directory not accessible: {backup_dir}"
        logger.error(msg)
        _write_status("error", msg)
        return {"status": "error", "message": msg}

    # Build the pg_dump connection string from settings
    db_host = settings.POSTGRES_HOST
    db_port = str(settings.POSTGRES_PORT)
    db_user = settings.POSTGRES_USER
    db_name = settings.POSTGRES_DB

    try:
        logger.info("Starting backup to %s", filepath)

        # Run pg_dump and pipe through gzip
        result = subprocess.run(
            [
                "pg_dump",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-d", db_name,
                "--no-password",
            ],
            capture_output=True,
            timeout=600,  # 10 minute timeout
            env={**os.environ, "PGPASSWORD": settings.POSTGRES_PASSWORD},
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[:500]
            msg = f"pg_dump failed: {stderr}"
            logger.error(msg)
            _write_status("error", msg)
            return {"status": "error", "message": msg}

        # Compress and write
        with gzip.open(filepath, "wb") as f:
            f.write(result.stdout)

        # Verify non-empty
        size = os.path.getsize(filepath)
        if size == 0:
            os.remove(filepath)
            msg = "Backup file was empty"
            logger.error(msg)
            _write_status("error", msg)
            return {"status": "error", "message": msg}

        # Human-readable size
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size / 1024:.1f} KB"

        # Prune old backups
        _prune_old_backups(backup_dir)

        msg = f"{filename} ({size_str})"
        logger.info("Backup complete: %s", msg)
        _write_status("success", msg)
        return {"status": "success", "message": msg}

    except subprocess.TimeoutExpired:
        msg = "pg_dump timed out after 10 minutes"
        logger.error(msg)
        _write_status("error", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        msg = f"Backup failed: {exc}"
        logger.error(msg)
        _write_status("error", msg)
        raise self.retry(exc=exc, countdown=300)
