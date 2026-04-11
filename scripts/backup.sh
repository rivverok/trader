#!/usr/bin/env bash
# backup.sh — Dump PostgreSQL data + copy .env into a timestamped backup folder
# Usage:  ./scripts/backup.sh                       (creates backups/backup-YYYYMMDD-HHmmss/)
#         ./scripts/backup.sh /mnt/external/backups  (custom output directory)

set -euo pipefail

OUT_DIR="${1:-./backups}"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_DIR="$OUT_DIR/backup-$TIMESTAMP"

echo "=== AI Trader Backup ==="
echo "Destination: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# 1. PostgreSQL dump via the running container
echo ""
echo "[1/3] Dumping PostgreSQL database..."
docker compose exec -T postgres pg_dump -U trader -d trader --format=custom --compress=6 > "$BACKUP_DIR/trader.dump"
DUMP_SIZE=$(du -h "$BACKUP_DIR/trader.dump" | cut -f1)
echo "       Database dump: $DUMP_SIZE"

# 2. Copy .env (contains API keys and secrets)
echo "[2/3] Copying .env..."
if [ -f ".env" ]; then
    cp .env "$BACKUP_DIR/.env"
    echo "       .env copied"
else
    echo "       WARNING: .env not found"
fi

# 3. Summary with row counts
echo "[3/3] Verifying backup..."
COUNTS=$(docker compose exec -T postgres psql -U trader -d trader -t -A -c "
SELECT 'stocks: '          || COUNT(*) FROM stocks
UNION ALL SELECT 'articles: '        || COUNT(*) FROM news_articles
UNION ALL SELECT 'filings: '         || COUNT(*) FROM sec_filings
UNION ALL SELECT 'filing_analyses: ' || COUNT(*) FROM filing_analyses
UNION ALL SELECT 'alerts: '          || COUNT(*) FROM alerts
UNION ALL SELECT 'claude_usage: '    || COUNT(*) FROM claude_usage;
")

echo ""
echo "  Row counts at backup time:"
echo "$COUNTS" | while IFS= read -r line; do
    echo "    $line"
done

# Write manifest
cat > "$BACKUP_DIR/manifest.json" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "postgres_dump": "trader.dump",
  "env_file": ".env",
  "row_counts": $(echo "$COUNTS" | jq -R -s 'split("\n") | map(select(length > 0))')
}
EOF

echo ""
echo "=== Backup complete: $BACKUP_DIR ==="
echo "Copy this folder to another machine to restore."
