# backup.ps1 — Dump PostgreSQL database to USB/external drive
#
# Runs via Task Scheduler or manually. Writes status to the database
# so the app can display backup health on the config page.
#
# Usage:
#   .\scripts\backup.ps1                     (saves to .\backups\)
#   .\scripts\backup.ps1 -OutDir E:\backups  (saves to USB drive)

param(
    [string]$OutDir = ".\backups"
)

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$filename = "trader_${timestamp}.sql.gz"
$retainDays = 30

Write-Host "=== AI Trader Backup ===" -ForegroundColor Cyan
Write-Host "Destination: $OutDir\$filename"

# Create backup directory
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# Helper: write backup status to the database
function Write-BackupStatus {
    param([string]$Status, [string]$Message)
    $now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $sql = @"
INSERT INTO system_kv (key, value, updated_at) VALUES
  ('backup_last_status', '$Status', NOW()),
  ('backup_last_time', '$now', NOW()),
  ('backup_last_message', '$Message', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
"@
    docker compose exec -T postgres psql -U trader -d trader -q -c "$sql" 2>$null
}

# Check if database is running
$pgReady = docker compose exec -T postgres pg_isready -U trader 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Database is not running." -ForegroundColor Red
    Write-BackupStatus "error" "Database not running"
    exit 0
}

# Run the dump (pipe through gzip inside the container)
Write-Host "`n[1/2] Dumping PostgreSQL database..." -ForegroundColor Yellow
$dumpPath = Join-Path $OutDir $filename
cmd /c "docker compose exec -T postgres bash -c `"pg_dump -U trader trader | gzip`" > `"$dumpPath`""

$dumpSize = (Get-Item $dumpPath).Length
if ($dumpSize -eq 0) {
    Remove-Item -Force $dumpPath
    Write-Host "ERROR: Database dump is empty (0 bytes)." -ForegroundColor Red
    Write-BackupStatus "error" "Backup produced empty file"
    exit 0
}

$sizeMB = [math]::Round($dumpSize / 1MB, 1)
Write-Host "       Database dump: ${sizeMB} MB"
Write-BackupStatus "success" "Backup ${filename} (${sizeMB}MB)"

# Prune old backups
Write-Host "[2/2] Pruning backups older than $retainDays days..." -ForegroundColor Yellow
$cutoff = (Get-Date).AddDays(-$retainDays)
$old = Get-ChildItem -Path $OutDir -Filter "trader_*.sql.gz" -ErrorAction SilentlyContinue |
       Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "       Removed $($old.Count) old backup(s)"
}

$remaining = (Get-ChildItem -Path $OutDir -Filter "trader_*.sql.gz" -ErrorAction SilentlyContinue).Count
Write-Host "`n=== Backup complete: $remaining backup(s) on disk ===" -ForegroundColor Green
