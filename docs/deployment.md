# Deployment Guide

This guide covers deploying the AI Trading Platform on Ubuntu (production) and Windows (development), plus migrating data between servers.

---

## Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Docker Engine | 24+ | Includes Docker Compose v2 |
| RAM | 4 GB | 8 GB recommended for ML training |
| Disk | 20 GB free | SSD/NVMe strongly recommended |
| API Keys | See `.env.example` | Alpaca, Anthropic, Finnhub, FRED |

---

## 1. Ubuntu Server Deployment (Production)

### 1.1 Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker via official script
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (log out and back in after)
sudo usermod -aG docker $USER

# Verify
docker --version
docker compose version
```

### 1.2 Clone the Repository

```bash
cd /opt   # or wherever you keep projects
git clone <your-repo-url> trader
cd trader
```

### 1.3 Configure Environment

```bash
cp .env.example .env
nano .env
```

Fill in all required values — at minimum:

| Variable | Required | Where to get it |
|---|---|---|
| `POSTGRES_PASSWORD` | Yes | Choose a strong password |
| `SECRET_KEY` | Yes | `openssl rand -hex 32` |
| `ALPACA_API_KEY` | Yes | [alpaca.markets](https://app.alpaca.markets/paper/dashboard/overview) |
| `ALPACA_SECRET_KEY` | Yes | Same as above |
| `ANTHROPIC_API_KEY` | Yes | [console.anthropic.com](https://console.anthropic.com) |
| `FINNHUB_API_KEY` | Yes | [finnhub.io](https://finnhub.io) |
| `FRED_API_KEY` | Yes | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `SEC_EDGAR_USER_AGENT` | Yes | Your name and email |

### 1.4 Remove Development Overrides

The `docker-compose.override.yml` file enables hot-reload and exposes database ports. **Do not use it in production.**

```bash
# Either delete it or rename it so Docker Compose ignores it
mv docker-compose.override.yml docker-compose.override.yml.dev
```

### 1.5 Build and Start

```bash
docker compose build
docker compose up -d
```

This starts 6 services:

| Service | Role |
|---|---|
| `postgres` | TimescaleDB database |
| `redis` | Celery broker + cache (AOF persistence) |
| `api` | FastAPI backend (auto-runs Alembic migrations on startup) |
| `worker` | Celery worker (data collection, analysis, ML) |
| `scheduler` | Celery Beat (cron-based task scheduling) |
| `frontend` | Next.js UI on port **5000** |

### 1.6 Verify

```bash
# All 6 services should show "Up" or "Up (healthy)"
docker compose ps

# Check API health
curl http://localhost:5000/api/health

# Tail logs
docker compose logs -f --tail=50
```

The app is accessible at `http://<hostname>:5000`.

### 1.7 Reverse Proxy with Caddy (Optional)

If you're already running Caddy on the server for other projects, add a block to your existing Caddyfile:

```
trader.example.com {
    reverse_proxy localhost:5000
}
```

Then reload Caddy:

```bash
sudo systemctl reload caddy
```

### 1.8 Auto-Start on Boot

Docker services are set to `restart: unless-stopped`, so they automatically restart after a reboot as long as the Docker daemon starts (which it does by default on Ubuntu).

Verify Docker is enabled:

```bash
sudo systemctl is-enabled docker
# Should say "enabled"
```

---

## 2. Windows Deployment (Development)

### 2.1 Install Docker Desktop

1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Install and enable **WSL 2 backend** when prompted
3. Restart your PC
4. Open Docker Desktop and wait for it to finish starting

Verify in PowerShell:

```powershell
docker --version
docker compose version
```

### 2.2 Clone the Repository

```powershell
cd C:\projects
git clone <your-repo-url> trader
cd trader
```

### 2.3 Configure Environment

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in all API keys and passwords (same table as section 1.3).

### 2.4 Build and Start (Development Mode)

On Windows, the `docker-compose.override.yml` is automatically loaded, enabling:
- Hot-reload on backend code changes
- PostgreSQL exposed on `localhost:5432`
- Redis exposed on `localhost:6379`
- Debug-level logging on worker and scheduler

```powershell
docker compose build
docker compose up -d
```

### 2.5 Build and Start (Production Mode)

To run without dev overrides on Windows:

```powershell
# Rename the override file
Rename-Item docker-compose.override.yml docker-compose.override.yml.dev

# Build and start
docker compose build
docker compose up -d
```

### 2.6 Verify

```powershell
docker compose ps
curl http://localhost:5000/api/health
```

The app is accessible at `http://localhost:5000`.

---

## 3. Transferring Data Between Servers

Use the backup/restore scripts to migrate all database data and configuration between machines.

### 3.1 Create a Backup (Source Machine)

From the project root:

**Windows:**
```powershell
.\scripts\backup.ps1
.\scripts\backup.ps1 -OutDir D:\my-backups   # custom output
```

**Ubuntu:**
```bash
./scripts/backup.sh
./scripts/backup.sh /mnt/external/backups   # custom output
```

This creates a folder under `backups/` containing:

| File | Contents |
|---|---|
| `trader.dump` | Full PostgreSQL database (pg_dump custom format) |
| `.env` | Environment configuration and API keys |
| `manifest.json` | Timestamp and row counts for verification |

The script prints row counts so you can verify the backup captured everything.

### 3.2 Transfer the Backup

Copy the entire backup folder to the destination machine. Options:

```bash
# SCP from Windows to Ubuntu
scp -r .\backups\backup-20260411-120000 user@riv-ubuntu:/opt/trader/backups/

# Or use rsync
rsync -avz .\backups\backup-20260411-120000\ user@riv-ubuntu:/opt/trader/backups/backup-20260411-120000/

# Or just use a USB drive / network share
```

### 3.3 Restore on the Destination Machine

**Windows (PowerShell):**

```powershell
cd C:\projects\trader
.\scripts\restore.ps1 -BackupDir .\backups\backup-20260411-120000
```

**Ubuntu (Bash):**

```bash
cd /opt/trader

# Make scripts executable (first time only)
chmod +x scripts/*.sh

./scripts/restore.sh ./backups/backup-20260411-120000
```

Both scripts perform the same steps: restore `.env` if missing, start PostgreSQL, drop/recreate the database, load the dump, and verify row counts.

### 3.4 Start All Services After Restore

```bash
docker compose up -d
```

The API container automatically runs Alembic migrations on startup, so the schema will be up to date even if the dump was from an older version.

### 3.5 Verify the Migration

```bash
# Check all services are healthy
docker compose ps

# Check the UI
curl http://localhost:5000/api/health

# Verify data is present
curl http://localhost:5000/api/stocks
```

---

## Troubleshooting

### Services won't start

```bash
docker compose logs api        # Check for migration errors
docker compose logs postgres   # Check for DB init errors
docker compose logs frontend   # Check for build errors
```

### Database connection errors

Make sure `POSTGRES_PASSWORD` in `.env` matches what was used when the volume was first created. If you changed the password, you need to delete the volume and re-restore:

```bash
docker compose down
docker volume rm trader_pgdata
docker compose up -d postgres
# Then run the restore steps again
```

### Port 5000 already in use

Change the host port in `docker-compose.yml`:

```yaml
frontend:
  ports:
    - "5001:5000"   # Map to host port 5001 instead
```

### Container name mismatch in restore

The restore script uses `trader-postgres-1` as the container name. If your Docker Compose project has a different name, find the actual container name:

```bash
docker compose ps postgres
# Use the NAME column in the docker cp command
```

### ARM64 / Apple Silicon / Raspberry Pi

TimescaleDB may not have official ARM64 images for all versions. Check [Docker Hub](https://hub.docker.com/r/timescale/timescaledb/tags) for available tags. If no ARM64 image exists, you can use plain PostgreSQL with reduced time-series performance:

```yaml
postgres:
  image: postgres:16
```
