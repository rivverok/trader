# backup.ps1 — Dump PostgreSQL data + copy .env into a timestamped backup folder
# Usage:  .\scripts\backup.ps1              (creates backups\backup-YYYYMMDD-HHmmss\)
#         .\scripts\backup.ps1 -OutDir D:\  (creates D:\backup-YYYYMMDD-HHmmss\)

param(
    [string]$OutDir = ".\backups"
)

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $OutDir "backup-$timestamp"

Write-Host "=== AI Trader Backup ===" -ForegroundColor Cyan
Write-Host "Destination: $backupDir"

# Create backup directory
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

# 1. PostgreSQL dump via the running container
Write-Host "`n[1/3] Dumping PostgreSQL database..." -ForegroundColor Yellow
$dumpPath = Join-Path $backupDir "trader.dump"
# Use cmd /c to avoid PowerShell's UTF-16 encoding corruption of binary data
cmd /c "docker compose exec -T postgres pg_dump -U trader -d trader --format=custom --compress=6 > `"$dumpPath`""

$dumpSize = (Get-Item (Join-Path $backupDir "trader.dump")).Length
Write-Host "       Database dump: $([math]::Round($dumpSize / 1MB, 1)) MB"

# 2. Copy .env (contains API keys and secrets)
Write-Host "[2/3] Copying .env..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Copy-Item ".env" (Join-Path $backupDir ".env")
    Write-Host "       .env copied"
} else {
    Write-Host "       WARNING: .env not found" -ForegroundColor Red
}

# 3. Summary with row counts
Write-Host "[3/3] Verifying backup..." -ForegroundColor Yellow
$counts = docker compose exec -T postgres psql -U trader -d trader -t -A -c @"
SELECT 'stocks: '            || COUNT(*) FROM stocks
UNION ALL SELECT 'articles: '          || COUNT(*) FROM news_articles
UNION ALL SELECT 'filings: '           || COUNT(*) FROM sec_filings
UNION ALL SELECT 'filing_analyses: '   || COUNT(*) FROM filing_analyses
UNION ALL SELECT 'alerts: '            || COUNT(*) FROM alerts
UNION ALL SELECT 'claude_usage: '      || COUNT(*) FROM claude_usage;
"@

Write-Host "`n  Row counts at backup time:" -ForegroundColor Gray
$counts | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }

# Write manifest
$manifest = @{
    timestamp = $timestamp
    postgres_dump = "trader.dump"
    env_file = ".env"
    row_counts = $counts
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $backupDir "manifest.json")

Write-Host "`n=== Backup complete: $backupDir ===" -ForegroundColor Green
Write-Host "Copy this folder to the new PC to restore."
