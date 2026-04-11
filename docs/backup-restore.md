# Backup, Restore & Migration

## Quick Reference

| Action | Windows (PowerShell) | Ubuntu (Bash) |
|--------|---------------------|---------------|
| Backup | `.\scripts\backup.ps1` | `./scripts/backup.sh` |
| Restore | `.\scripts\restore.ps1 -BackupDir .\backups\backup-YYYYMMDD-HHmmss` | `./scripts/restore.sh ./backups/backup-YYYYMMDD-HHmmss` |

---

## What Gets Backed Up

| Item | File | Contains |
|------|------|----------|
| PostgreSQL database | `trader.dump` | All tables: stocks, watchlist, articles, filings, analyses, alerts, Claude usage, Alembic migrations |
| Environment config | `.env` | API keys (Alpaca, Finnhub, FRED, Anthropic, EDGAR), DB passwords, model settings |

Redis is **not** backed up — it holds only the Celery task queue and result cache, which are ephemeral.

---

## Creating a Backup (source machine)

**Windows (PowerShell):**

```powershell
cd C:\projects\trader

# Default: saves to .\backups\backup-YYYYMMDD-HHmmss\
.\scripts\backup.ps1

# Or specify an output location (e.g. USB drive)
.\scripts\backup.ps1 -OutDir E:\
```

**Ubuntu (Bash):**

```bash
cd /opt/trader

# Default: saves to ./backups/backup-YYYYMMDD-HHmmss/
./scripts/backup.sh

# Or specify an output location
./scripts/backup.sh /mnt/external/backups
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

### Step-by-step (Windows)

```powershell
# 1. Copy the project to the new PC (git clone, USB, network share, etc.)
git clone <your-repo-url> C:\projects\trader
cd C:\projects\trader

# 2. Copy your backup folder into the project
Copy-Item -Recurse E:\backup-20260410-120000 .\backups\backup-20260410-120000

# 3. Restore (starts PostgreSQL, loads the dump, restores .env)
.\scripts\restore.ps1 -BackupDir .\backups\backup-20260410-120000

# 4. Build and start all services
docker compose build
docker compose up -d
```

### Step-by-step (Ubuntu)

```bash
# 1. Clone the project
git clone <your-repo-url> /opt/trader
cd /opt/trader

# 2. Copy your backup folder into the project
cp -r /tmp/backup-20260410-120000 ./backups/

# 3. Make scripts executable (first time only)
chmod +x scripts/*.sh

# 4. Restore (starts PostgreSQL, loads the dump, restores .env)
./scripts/restore.sh ./backups/backup-20260410-120000

# 5. Build and start all services
docker compose build
docker compose up -d
```

### If something goes wrong

```bash
# Check container status
docker compose ps

# Check logs
docker compose logs api --tail=20
docker compose logs worker --tail=20

# If the database restore failed, you can retry
docker compose down
docker volume rm trader_pgdata
# Windows: .\scripts\restore.ps1 -BackupDir .\backups\backup-20260410-120000
# Ubuntu:  ./scripts/restore.sh ./backups/backup-20260410-120000
docker compose up -d
```

---

## Network Access (running 24/7)

Once the platform is running on the dedicated PC, access it from other devices on your LAN:

1. Find the server's local IP:

   **Ubuntu:**
   ```bash
   hostname -I | awk '{print $1}'
   ```

   **Windows:**
   ```powershell
   (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet*","Wi-Fi*").IPAddress
   ```

2. Allow port 5000 through the firewall:

   **Ubuntu:**
   ```bash
   sudo ufw allow 5000/tcp
   ```

   **Windows (run as admin):**
   ```powershell
   New-NetFirewallRule -DisplayName "AI Trader" -Direction Inbound -Port 5000 -Protocol TCP -Action Allow
   ```

3. Access from any device on the network: `http://<server-ip>:5000`

---

## Routine Backups

Run backups periodically to protect your data. Old backups can be deleted manually.

**Windows:**

```powershell
# Weekly backup to a network share
.\scripts\backup.ps1 -OutDir \\NAS\backups\trader
```

**Ubuntu:**

```bash
# Weekly backup (add to crontab if desired)
./scripts/backup.sh /mnt/nas/trader-backups
```
