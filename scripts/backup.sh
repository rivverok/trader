#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# backup.sh — Dump PostgreSQL database to USB drive
#
# Runs via cron. Writes status to the database so the app can
# display backup health on the config page.
#
# Usage:
#   bash scripts/backup.sh
#
# Requires:
#   BACKUP_DIR env var or /mnt/backup/trader_bkups default
#
# Cron example (daily at 2 AM):
#   0 2 * * * cd /opt/trader/trader && bash scripts/backup.sh >> /var/log/trader-backup.log 2>&1
# ──────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

BACKUP_DIR="${BACKUP_DIR:-/mnt/backup/trader_bkups}"
RETAIN_DAYS=30
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="trader_${TIMESTAMP}.sql.gz"

# Helper: write backup status to the database
write_status() {
  local status="$1"   # success | error
  local message="$2"
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  docker compose exec -T postgres psql -U "${POSTGRES_USER:-trader}" "${POSTGRES_DB:-trader}" -q <<SQL
INSERT INTO system_kv (key, value, updated_at)
VALUES
  ('backup_last_status', '${status}', NOW()),
  ('backup_last_time', '${now}', NOW()),
  ('backup_last_message', '${message}', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
SQL
}

# Source .env if it exists (for POSTGRES_USER, POSTGRES_DB, BACKUP_DIR overrides)
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

# Re-apply default after sourcing .env (in case BACKUP_DIR was set there)
BACKUP_DIR="${BACKUP_DIR:-/mnt/backup/trader_bkups}"

# Check if backup directory is accessible
if [ ! -d "$BACKUP_DIR" ]; then
  mkdir -p "$BACKUP_DIR" 2>/dev/null || true
fi

if [ ! -d "$BACKUP_DIR" ] || [ ! -w "$BACKUP_DIR" ]; then
  echo "$(date): Backup directory $BACKUP_DIR not accessible (USB drive not mounted?). Skipping."
  write_status "error" "Backup drive not accessible at ${BACKUP_DIR}" || true
  exit 0
fi

# Check if database is running
if ! docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-trader}" -q 2>/dev/null; then
  echo "$(date): Database is not running. Skipping backup."
  write_status "error" "Database not running" || true
  exit 0
fi

# Run the dump
echo "$(date): Starting backup to ${BACKUP_DIR}/${FILENAME}..."
if docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-trader}" "${POSTGRES_DB:-trader}" | gzip > "${BACKUP_DIR}/${FILENAME}"; then
  # Verify the file isn't empty
  if [ -s "${BACKUP_DIR}/${FILENAME}" ]; then
    SIZE=$(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1)
    echo "$(date): Backup complete — ${FILENAME} (${SIZE})"
    write_status "success" "Backup ${FILENAME} (${SIZE})"
  else
    rm -f "${BACKUP_DIR}/${FILENAME}"
    echo "$(date): Backup file was empty. Removed."
    write_status "error" "Backup produced empty file"
    exit 0
  fi
else
  rm -f "${BACKUP_DIR}/${FILENAME}"
  echo "$(date): pg_dump failed."
  write_status "error" "pg_dump failed"
  exit 0
fi

# Prune old backups
echo "$(date): Pruning backups older than ${RETAIN_DAYS} days..."
find "$BACKUP_DIR" -name "trader_*.sql.gz" -mtime +${RETAIN_DAYS} -delete 2>/dev/null || true

COUNT=$(find "$BACKUP_DIR" -name "trader_*.sql.gz" | wc -l)
echo "$(date): ${COUNT} backup(s) on disk."
