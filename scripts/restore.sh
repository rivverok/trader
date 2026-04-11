#!/usr/bin/env bash
# restore.sh — Restore a backup created by backup.sh/backup.ps1 into a running Docker Compose stack
# Usage:  ./scripts/restore.sh ./backups/backup-20260411-090554

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-directory>"
    echo "Example: $0 ./backups/backup-20260411-090554"
    exit 1
fi

BACKUP_DIR="$1"
DUMP_FILE="$BACKUP_DIR/trader.dump"
ENV_FILE="$BACKUP_DIR/.env"
COMPOSE_PROJECT="trader"

echo "=== AI Trader Restore ==="
echo "Source: $BACKUP_DIR"

# Validate backup
if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: trader.dump not found in $BACKUP_DIR"
    exit 1
fi

# Show manifest if it exists
if [ -f "$BACKUP_DIR/manifest.json" ]; then
    MANIFEST_TS=$(grep -o '"timestamp": *"[^"]*"' "$BACKUP_DIR/manifest.json" | head -1 | cut -d'"' -f4)
    echo "Backup timestamp: $MANIFEST_TS"
fi

# 1. Restore .env if not already present
echo ""
echo "[1/4] Checking .env..."
if [ -f "$ENV_FILE" ] && [ ! -f ".env" ]; then
    cp "$ENV_FILE" .env
    echo "       .env restored from backup"
elif [ -f ".env" ]; then
    echo "       .env already exists — skipping (compare manually if needed)"
else
    echo "       ERROR: No .env in backup and none in project"
    exit 1
fi

# 2. Make sure postgres is running
echo "[2/4] Ensuring PostgreSQL is running..."
docker compose up -d postgres
echo "       Waiting for healthy..."
ATTEMPTS=0
until docker compose exec -T postgres pg_isready -U trader > /dev/null 2>&1; do
    sleep 2
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ $ATTEMPTS -ge 15 ]; then
        echo "ERROR: PostgreSQL not healthy after 30s"
        exit 1
    fi
done
echo "       PostgreSQL is ready"

# 3. Drop and recreate the database (clean restore)
echo "[3/4] Restoring database from dump..."
echo "       Dropping existing data and restoring..."

# Terminate existing connections then drop/recreate
docker compose exec -T postgres psql -U trader -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'trader' AND pid != pg_backend_pid();" > /dev/null 2>&1 || true

docker compose exec -T postgres dropdb -U trader --if-exists trader
docker compose exec -T postgres createdb -U trader trader

# Restore the dump — copy into container for safety
docker cp "$DUMP_FILE" "${COMPOSE_PROJECT}-postgres-1:/tmp/trader.dump"
docker compose exec -T postgres pg_restore -U trader -d trader --no-owner --role=trader --disable-triggers /tmp/trader.dump
docker compose exec -T postgres rm /tmp/trader.dump

echo "       Database restored"

# 4. Verify
echo "[4/4] Verifying restore..."
COUNTS=$(docker compose exec -T postgres psql -U trader -d trader -t -A -c "
SELECT 'stocks: '          || COUNT(*) FROM stocks
UNION ALL SELECT 'articles: '        || COUNT(*) FROM news_articles
UNION ALL SELECT 'filings: '         || COUNT(*) FROM sec_filings
UNION ALL SELECT 'filing_analyses: ' || COUNT(*) FROM filing_analyses
UNION ALL SELECT 'alerts: '          || COUNT(*) FROM alerts
UNION ALL SELECT 'claude_usage: '    || COUNT(*) FROM claude_usage;
")

echo ""
echo "  Row counts after restore:"
echo "$COUNTS" | while IFS= read -r line; do
    echo "    $line"
done

echo ""
echo "=== Restore complete ==="
echo "Now run:  docker compose up -d"
