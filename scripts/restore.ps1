# restore.ps1 — Restore a backup created by backup.ps1 into a running Docker Compose stack
# Usage:  .\scripts\restore.ps1 -BackupDir .\backups\backup-20260410-120000

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupDir
)

$ErrorActionPreference = "Stop"

$dumpFile = Join-Path $BackupDir "trader.dump"
$envFile  = Join-Path $BackupDir ".env"
$composeProject = "trader"

Write-Host "=== AI Trader Restore ===" -ForegroundColor Cyan
Write-Host "Source: $BackupDir"

# Validate backup
if (-not (Test-Path $dumpFile)) {
    Write-Host "ERROR: trader.dump not found in $BackupDir" -ForegroundColor Red
    exit 1
}

# Show manifest if it exists
$manifestFile = Join-Path $BackupDir "manifest.json"
if (Test-Path $manifestFile) {
    $manifest = Get-Content $manifestFile | ConvertFrom-Json
    Write-Host "Backup timestamp: $($manifest.timestamp)" -ForegroundColor Gray
}

# 1. Restore .env if not already present
Write-Host "`n[1/4] Checking .env..." -ForegroundColor Yellow
if ((Test-Path $envFile) -and -not (Test-Path ".env")) {
    Copy-Item $envFile ".env"
    Write-Host "       .env restored from backup"
} elseif (Test-Path ".env") {
    Write-Host "       .env already exists — skipping (compare manually if needed)"
} else {
    Write-Host "       WARNING: No .env in backup and none in project" -ForegroundColor Red
    exit 1
}

# 2. Make sure postgres is running
Write-Host "[2/4] Ensuring PostgreSQL is running..." -ForegroundColor Yellow
docker compose up -d postgres
Write-Host "       Waiting for healthy..."
$attempts = 0
do {
    Start-Sleep -Seconds 2
    $health = docker compose exec -T postgres pg_isready -U trader 2>&1
    $attempts++
} while ($LASTEXITCODE -ne 0 -and $attempts -lt 15)

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PostgreSQL not healthy after 30s" -ForegroundColor Red
    exit 1
}
Write-Host "       PostgreSQL is ready"

# 3. Drop and recreate the database (clean restore)
Write-Host "[3/4] Restoring database from dump..." -ForegroundColor Yellow
Write-Host "       Dropping existing data and restoring..." -ForegroundColor Gray

# Terminate existing connections then drop/recreate
docker compose exec -T postgres psql -U trader -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'trader' AND pid != pg_backend_pid();" 2>&1 | Out-Null

docker compose exec -T postgres dropdb -U trader --if-exists trader
docker compose exec -T postgres createdb -U trader trader

# Enable TimescaleDB extension before restore
docker compose exec -T postgres psql -U trader -d trader -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

# Restore the dump — copy into container, use TimescaleDB pre/post hooks
docker cp $dumpFile "${composeProject}-postgres-1:/tmp/trader.dump"
docker compose exec -T postgres psql -U trader -d trader -c "SELECT timescaledb_pre_restore();"
docker compose exec -T postgres pg_restore -U trader -d trader --no-owner --role=trader --disable-triggers /tmp/trader.dump
docker compose exec -T postgres psql -U trader -d trader -c "SELECT timescaledb_post_restore();"
docker compose exec -T postgres rm /tmp/trader.dump

Write-Host "       Database restored"

# 4. Verify
Write-Host "[4/4] Verifying restore..." -ForegroundColor Yellow
$verifySQL = "SELECT 'stocks: ' || COUNT(*) FROM stocks UNION ALL SELECT 'articles: ' || COUNT(*) FROM news_articles UNION ALL SELECT 'filings: ' || COUNT(*) FROM sec_filings UNION ALL SELECT 'filing_analyses: ' || COUNT(*) FROM filing_analyses UNION ALL SELECT 'alerts: ' || COUNT(*) FROM alerts UNION ALL SELECT 'claude_usage: ' || COUNT(*) FROM claude_usage;"
$counts = docker compose exec -T postgres psql -U trader -d trader -t -A -c $verifySQL

Write-Host "`n  Row counts after restore:" -ForegroundColor Gray
$counts | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }

Write-Host "`n=== Restore complete ===" -ForegroundColor Green
Write-Host "Now run:  docker compose up -d"
