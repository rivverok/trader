# Backup, Restore & Migration

## Quick Reference

| Action | Command |
|--------|---------|
| Backup | `.\scripts\backup.ps1` |
| Restore | `.\scripts\restore.ps1 -BackupDir .\backups\backup-YYYYMMDD-HHmmss` |

---

## What Gets Backed Up

| Item | File | Contains |
|------|------|----------|
| PostgreSQL database | `trader.dump` | All tables: stocks, watchlist, articles, filings, analyses, alerts, Claude usage, Alembic migrations |
| Environment config | `.env` | API keys (Alpaca, Finnhub, FRED, Anthropic, EDGAR), DB passwords, model settings |

Redis is **not** backed up — it holds only the Celery task queue and result cache, which are ephemeral.

---

## Creating a Backup (source PC)

```powershell
cd C:\projects\trader

# Default: saves to .\backups\backup-YYYYMMDD-HHmmss\
.\scripts\backup.ps1

# Or specify an output location (e.g. USB drive)
.\scripts\backup.ps1 -OutDir E:\
```

The script will:
1. Dump the PostgreSQL database via `pg_dump` (compressed custom format)
2. Copy your `.env` file
3. Print row counts for verification
4. Write a `manifest.json` with metadata

Typical backup size: ~10–50 MB depending on how many articles/filings are stored.

---

## Migrating to a New PC

### Prerequisites on the new PC

1. **Docker Desktop** installed and running
2. **Git** (to clone or copy the project)

### Step-by-step

```powershell
# 1. Copy the project to the new PC (git clone, USB, network share, etc.)
#    Example with git:
git clone <your-repo-url> C:\projects\trader
cd C:\projects\trader

#    Or just copy the entire project folder — either works.

# 2. Copy your backup folder into the project
#    Example: copy from USB drive
Copy-Item -Recurse E:\backup-20260410-120000 .\backups\backup-20260410-120000

# 3. Restore (this starts PostgreSQL, loads the dump, and restores .env)
.\scripts\restore.ps1 -BackupDir .\backups\backup-20260410-120000

# 4. Build and start all services
docker compose build
docker compose up -d

# 5. Verify everything is running
#    Open http://localhost in a browser
#    Check the Status page — all services should be green
```

### If something goes wrong

```powershell
# Check container status
docker compose ps

# Check logs
docker compose logs api --tail=20
docker compose logs worker --tail=20

# If the database restore failed, you can retry
docker compose down
docker volume rm trader_pgdata
.\scripts\restore.ps1 -BackupDir .\backups\backup-20260410-120000
docker compose up -d
```

---

## Network Access (running 24/7)

Once the platform is running on the dedicated PC, access it from other devices on your LAN:

1. Find the server PC's local IP:
   ```powershell
   (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet*","Wi-Fi*").IPAddress
   ```

2. Update `.env` on the server:
   ```
   CADDY_SITE_ADDRESS=192.168.x.x
   ```

3. Restart Caddy:
   ```powershell
   docker compose up -d --force-recreate caddy
   ```

4. Allow port 80 through Windows Firewall (run as admin):
   ```powershell
   New-NetFirewallRule -DisplayName "AI Trader HTTP" -Direction Inbound -Port 80 -Protocol TCP -Action Allow
   ```

5. Access from any device on the network: `http://192.168.x.x`

---

## Routine Backups

Run backups periodically to protect your data. Old backups can be deleted manually.

```powershell
# Weekly backup to a network share
.\scripts\backup.ps1 -OutDir \\NAS\backups\trader
```
