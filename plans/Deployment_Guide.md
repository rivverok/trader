# AI Trading Platform — Deployment Guide

Everything you need to sign up for, install, configure, and launch.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [External Services & Signups](#2-external-services--signups)
3. [Environment Configuration](#3-environment-configuration)
4. [First-Time Deployment](#4-first-time-deployment)
5. [Database Migrations](#5-database-migrations)
6. [Docker Services Overview](#6-docker-services-overview)
7. [Caddy / HTTPS / Networking](#7-caddy--https--networking)
8. [Scheduled Tasks (Celery Beat)](#8-scheduled-tasks-celery-beat)
9. [Development Mode](#9-development-mode)
10. [Going Live (Paper → Real Money)](#10-going-live-paper--real-money)
11. [Monitoring & Maintenance](#11-monitoring--maintenance)
12. [Cost Estimates](#12-cost-estimates)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB |
| Storage | 40 GB SSD | 100 GB SSD |
| Network | Always-on broadband | Wired ethernet, low-latency |

The platform is designed to run 24/7 on a home server, mini-PC, or VPS. Market-hours tasks need reliable connectivity during US market hours (9:30 AM – 4:00 PM ET, Mon–Fri).

### Software

| Software | Version | What It Is | Install Link |
|----------|---------|------------|-------------|
| **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux) | 24+ | Container runtime — runs all 7 services in isolated containers so you don't install Python, Node, Postgres, etc. on your host | [docker.com/get-started](https://docs.docker.com/get-started/get-docker/) |
| **Docker Compose** | v2+ | Multi-container orchestration — bundled with Docker Desktop, or install separately on Linux | Included with Docker Desktop |
| **Git** | 2.x | Source code management — to clone/update the project | [git-scm.com](https://git-scm.com/downloads) |

That's it. Everything else (Python 3.11, Node.js 20, PostgreSQL 16, Redis 7) runs inside Docker containers.

---

## 2. External Services & Signups

You need **5 external accounts**. All have free tiers except Anthropic (pay-per-use).

### 2.1 Alpaca — Stock Broker & Market Data

| | |
|---|---|
| **What it does** | Executes buy/sell orders and provides real-time stock prices, daily bars, and account/portfolio data. Paper trading mode gives you a simulated $100K account to test with. |
| **Cost** | Free (paper trading). Live trading requires a funded brokerage account (no minimum, but pattern day trading rules apply under $25K). |
| **Sign up** | [alpaca.markets](https://alpaca.markets) |

**Steps:**
1. Create an Alpaca account
2. Go to **Paper Trading** → **Overview** → **API Keys**
3. Click **Generate New Keys**
4. Copy the **API Key ID** and **Secret Key** (the secret is only shown once)
5. Save both for your `.env` file

> **Important:** Paper trading and live trading have *separate* API keys. Start with paper.

### 2.2 Anthropic — Claude AI

| | |
|---|---|
| **What it does** | Powers all AI analysis: news sentiment scoring, SEC filing analysis, multi-source context synthesis, and trade decision reasoning. Uses Claude Haiku (fast/cheap) for simple tasks and Claude Sonnet (smarter/pricier) for complex analysis. |
| **Cost** | Pay-per-use. Estimated ~$80–120/month depending on watchlist size and task frequency. |
| **Sign up** | [console.anthropic.com](https://console.anthropic.com) |

**Steps:**
1. Create an Anthropic account
2. Go to **Plans & Billing** → add a payment method
3. Go to **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-...`)
5. Save for your `.env` file

> **Tip:** Set a monthly spending limit in the Anthropic console. Start with $50 and increase once you see actual usage patterns.

### 2.3 Finnhub — Financial News & Company Data

| | |
|---|---|
| **What it does** | Provides real-time financial news articles and company profile data (sector, industry, market cap). The platform collects news every 30 minutes and feeds it to Claude for sentiment analysis. |
| **Cost** | Free (60 API calls per minute — more than enough). |
| **Sign up** | [finnhub.io](https://finnhub.io) |

**Steps:**
1. Create an account
2. Your API token is auto-generated and shown on the dashboard
3. Copy the token
4. Save for your `.env` file

### 2.4 FRED — Federal Reserve Economic Data

| | |
|---|---|
| **What it does** | Provides macroeconomic indicators: GDP growth, unemployment rate, CPI/inflation, federal funds rate, yield curve, housing data. These feed into Claude's market context synthesis so decisions account for the economic backdrop. |
| **Cost** | Completely free, unlimited API calls. |
| **Sign up** | [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) |

**Steps:**
1. Create a FRED account
2. Request an API key (instant approval)
3. Copy the key
4. Save for your `.env` file

### 2.5 SEC EDGAR — Corporate Filings

| | |
|---|---|
| **What it does** | Provides 10-K (annual) and 10-Q (quarterly) corporate filings from the SEC. The platform downloads these and sends them to Claude for financial analysis (revenue trends, margin analysis, risk factor changes, forward guidance). |
| **Cost** | Free. No API key required. |
| **Sign up** | None needed |

**Setup:**
- SEC requires a `User-Agent` header with your name and email so they can contact you if your scraping causes issues
- Set `SEC_EDGAR_USER_AGENT` in your `.env` to something like: `John Doe john@example.com`

---

## 3. Environment Configuration

### 3.1 Create Your `.env` File

```bash
cd c:\projects\trader
copy .env.example .env
```

Open `.env` in a text editor and fill in all the blank values. The file has inline comments explaining each setting.

### 3.2 Required Values (Must Set)

These **must** be filled in or the platform won't start:

| Variable | Where to Get It |
|----------|----------------|
| `SECRET_KEY` | Generate with: `openssl rand -hex 32` (or any random 32+ char string) |
| `POSTGRES_PASSWORD` | Choose a strong password (only used internally between Docker containers) |
| `ALPACA_API_KEY` | Alpaca dashboard → Paper Trading → API Keys |
| `ALPACA_SECRET_KEY` | Alpaca dashboard → Paper Trading → API Keys |
| `ANTHROPIC_API_KEY` | Anthropic console → API Keys |
| `FINNHUB_API_KEY` | Finnhub dashboard → API Token |
| `FRED_API_KEY` | FRED website → API Keys |
| `SEC_EDGAR_USER_AGENT` | Your name + email, e.g. `Jane Doe jane@example.com` |

### 3.3 Risk & Trading Defaults (Can Adjust Later)

These have sensible defaults. You can tune them in the `.env` or via the web UI at runtime:

| Variable | Default | What It Controls |
|----------|---------|-----------------|
| `RISK_MAX_TRADE_DOLLARS` | `1000` | Maximum dollar amount for a single trade |
| `RISK_MAX_POSITION_PCT` | `10` | No single stock can exceed this % of portfolio |
| `RISK_MAX_SECTOR_PCT` | `25` | No single sector can exceed this % of portfolio |
| `RISK_DAILY_LOSS_LIMIT` | `500` | If daily realized losses exceed this $, **all trading halts** (circuit breaker) |
| `RISK_MAX_DRAWDOWN_PCT` | `15` | If portfolio drops this % from its peak, **all trading halts** (circuit breaker) |
| `RISK_MIN_CONFIDENCE` | `0.6` | Trades below this confidence score are rejected (0.0–1.0) |
| `AUTO_EXECUTE` | `false` | `false` = you manually approve each trade. `true` = auto-execute. **Start with false.** |
| `SIGNAL_WEIGHT_ML` | `0.3` | Weight for ML model signals (XGBoost / LightGBM) |
| `SIGNAL_WEIGHT_CLAUDE` | `0.4` | Weight for Claude AI analysis |
| `SIGNAL_WEIGHT_ANALYST` | `0.3` | Weight for your personal analyst inputs |

> Signal weights must sum to 1.0.

### 3.4 Task Frequency Defaults (Can Adjust)

These control how often background tasks run. Defaults are reasonable for a ~10 stock watchlist:

| Variable | Default | Description |
|----------|---------|-------------|
| `COLLECT_PRICES_INTERVAL_SEC` | `60` | Price collection during market hours |
| `COLLECT_NEWS_INTERVAL_SEC` | `1800` | News collection (30 min) |
| `COLLECT_ECONOMIC_INTERVAL_SEC` | `86400` | Economic data (daily) |
| `COLLECT_FILINGS_INTERVAL_SEC` | `21600` | SEC filings (6 hours) |
| `ANALYZE_NEWS_INTERVAL_SEC` | `900` | Claude news analysis (15 min) |
| `ANALYZE_FILINGS_INTERVAL_SEC` | `3600` | Claude filing analysis (1 hour) |
| `CONTEXT_SYNTHESIS_INTERVAL_SEC` | `7200` | Claude full synthesis (2 hours) |
| `DECISION_CYCLE_INTERVAL_SEC` | `1800` | Trade decision engine (30 min) |
| `ML_SIGNAL_INTERVAL_SEC` | `3600` | ML signal generation (1 hour) |
| `PORTFOLIO_SYNC_INTERVAL_SEC` | `300` | Alpaca portfolio sync (5 min) |

> Higher-frequency Claude tasks = higher Anthropic bill. Reduce `ANALYZE_NEWS_INTERVAL_SEC` and `CONTEXT_SYNTHESIS_INTERVAL_SEC` if cost is a concern.

---

## 4. First-Time Deployment

### 4.1 Clone and Configure

```bash
git clone <your-repo-url> c:\projects\trader
cd c:\projects\trader
copy .env.example .env
# Edit .env with your API keys and passwords
```

### 4.2 Build and Start

```bash
# Build all container images (first time takes 5-10 minutes)
docker compose build

# Start everything
docker compose up -d
```

This starts all 7 services in the background. Docker will:
1. Pull base images (PostgreSQL, Redis, Caddy, Python, Node.js)
2. Build the backend and frontend images
3. Start services in dependency order (postgres → redis → api → worker/scheduler → frontend → caddy)

### 4.3 Run Database Migrations

```bash
# Run all Alembic migrations to set up the database schema
docker compose exec api alembic upgrade head
```

This creates all 20+ tables across 7 migration files: stocks, prices, news, economic indicators, SEC filings, analysis results, ML models/signals, trades, portfolio, risk state, and alerts.

### 4.4 Verify

```bash
# Check all services are running
docker compose ps

# Check health endpoint
curl https://localhost/api/health
# Should return: {"status":"ok","trading_mode":"paper","database":"ok","redis":"ok"}
```

Open your browser to `https://localhost` (accept the self-signed certificate warning if using `:443`).

### 4.5 Stock Watchlist

The AI manages the watchlist automatically via the **Watchlist** page. It runs a discovery cycle (Tue/Thu at 7 AM ET) that analyzes economic conditions, sector trends, and market data to decide which stocks to track. You can:

- **Let the AI build it from scratch** — if the watchlist is empty on first discovery run, it will create a diversified starting watchlist
- **Submit hints** — use the "Suggest to AI" panel to suggest sectors, themes, or specific symbols (e.g., "look into EV stocks", "consider NVDA"). The AI considers your input but makes its own decisions.
- **Manually add stocks** — from the Dashboard, use the "Add Symbol" input to force-add a stock. The AI won't remove manually-held positions.
- **Trigger discovery manually** — click "Run Discovery Now" on the Watchlist page anytime

The AI logs every add/remove decision with full reasoning in the Discovery Log.

---

## 5. Database Migrations

The platform uses **Alembic** for database schema management. Migrations live in `backend/alembic/versions/`.

| Migration | What It Creates |
|-----------|----------------|
| `0001_initial_schema` | Core tables: stocks, price_bars, watchlist |
| `0002_add_economic_and_sec_tables` | Economic indicators (FRED), SEC filings |
| `0003_add_analysis_tables` | News analysis, filing analysis, context synthesis, Claude usage tracking |
| `0004_add_ml_tables` | ML signals, model registry, backtest results |
| `0005_add_decision_engine_tables` | Proposed trades, analyst inputs, risk state |
| `0006_add_execution_engine_columns` | Trade execution, portfolio positions/snapshots |
| `0007_add_alerts_table` | Real-time alert/notification storage |
| `0008_add_autonomous_mode` | Autonomous mode flag on risk state |
| `0009_add_discovery_tables` | AI watchlist discovery: hints + decision log |

**Commands:**

```bash
# Apply all pending migrations
docker compose exec api alembic upgrade head

# Check current migration version
docker compose exec api alembic current

# Roll back one migration (if needed)
docker compose exec api alembic downgrade -1
```

---

## 6. Docker Services Overview

The platform runs as **7 Docker containers** orchestrated by Docker Compose:

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────┐
│             Caddy  (ports 80, 443)              │
│         HTTPS termination + routing             │
├───────────────────┬─────────────────────────────┤
│  /api/* /ws/*     │         everything else     │
│       ▼           │              ▼              │
│  ┌──────────┐     │      ┌─────────────┐       │
│  │ FastAPI  │     │      │   Next.js   │       │
│  │  :8000   │     │      │   :3000     │       │
│  └────┬─────┘     │      └─────────────┘       │
│       │           │                             │
│  ┌────▼──────┐  ┌─┴──────────┐                  │
│  │PostgreSQL │  │   Redis    │                  │
│  │  :5432    │  │   :6379    │                  │
│  └───────────┘  └──────┬─────┘                  │
│                        │                        │
│               ┌────────▼──────────┐             │
│               │  Celery Worker    │             │
│               │  Celery Scheduler │             │
│               └───────────────────┘             │
└─────────────────────────────────────────────────┘
```

| Service | Image | Purpose |
|---------|-------|---------|
| **postgres** | `timescale/timescaledb:latest-pg16` | Primary database. PostgreSQL 16 with TimescaleDB extension for efficient time-series queries on price history. Stores everything: stocks, prices, news, analysis, trades, portfolio. |
| **redis** | `redis:7-alpine` | Two roles: (1) message broker for Celery task queue, (2) caching layer. Lightweight, fast. |
| **api** | Built from `./backend` | The FastAPI application server. Serves 13 REST API routers + WebSocket endpoint for alerts. All business logic lives here. |
| **worker** | Same image as api | Celery worker that picks up and executes async tasks: data collection, Claude analysis, ML signals, trade execution, portfolio sync. Runs with 2 concurrent worker threads. |
| **scheduler** | Same image as api | Celery Beat scheduler. Sends tasks to the worker on a cron schedule (see section 8). Runs 24/7, scheduling market-hours-only tasks and always-on tasks separately. |
| **frontend** | Built from `./frontend` | Next.js 14 React app. Provides the web dashboard: portfolio view, signals, trades, analytics, alerts, configuration. Multi-stage Docker build for a ~200MB production image. |
| **caddy** | `caddy:2-alpine` | Reverse proxy. Routes `/api/*` and `/ws/*` to FastAPI, everything else to Next.js. Auto-generates HTTPS certificates (self-signed for localhost, Let's Encrypt for real domains). |

### Persistent Volumes

| Volume | Service | What's Stored |
|--------|---------|---------------|
| `pgdata` | postgres | All database data. **Back this up.** |
| `redisdata` | redis | Redis persistence (task state, cache). Recreatable. |
| `caddy_data` | caddy | HTTPS certificate + ACME account. |
| `caddy_config` | caddy | Caddy runtime config. |

---

## 7. Caddy / HTTPS / Networking

### Local Access (Default)

With the default `CADDY_SITE_ADDRESS=:443`:
- Open `https://localhost` in your browser
- Accept the self-signed certificate warning (it's a valid cert, just not issued by a public CA)
- API available at `https://localhost/api/health`

### LAN Access (Other Devices)

To access from another device on your local network:
1. Find your machine's LAN IP (e.g., `192.168.1.50`)
2. Open `https://192.168.1.50` from another device
3. Accept the certificate warning

### Public Domain (Optional)

If you own a domain and want external access with a real HTTPS certificate:

1. Point your domain's DNS A record to your server's public IP
2. Set `CADDY_SITE_ADDRESS=trader.yourdomain.com` in `.env`
3. Forward ports 80 and 443 from your router to the server
4. Restart Caddy: `docker compose restart caddy`
5. Caddy will automatically obtain a Let's Encrypt certificate

### Port Summary

| Port | Protocol | Service | Exposed By |
|------|----------|---------|------------|
| 80 | HTTP | Caddy (redirects to 443) | Docker → Host |
| 443 | HTTPS | Caddy (main entry) | Docker → Host |
| 8000 | HTTP | FastAPI (internal only in prod) | Only in dev |
| 3000 | HTTP | Next.js (internal only in prod) | Only in dev |
| 5432 | TCP | PostgreSQL (internal only) | Never exposed |
| 6379 | TCP | Redis (internal only) | Never exposed |

---

## 8. Scheduled Tasks (Celery Beat)

The platform runs **16 automated tasks** on schedules, managed by Celery Beat. All times are **US/Eastern**.

### Market-Hours Tasks (Mon–Fri, ~9:30 AM – 4:00 PM ET)

| Task | Frequency | What It Does |
|------|-----------|-------------|
| Collect Prices | Every 1 min | Fetches latest stock prices from Alpaca for all watchlist stocks |
| Generate ML Signals | Every 1 hour | Runs XGBoost/LightGBM models on technical indicators to produce buy/hold/sell signals |
| Decision Cycle | Every 30 min | Aggregates ML + Claude + analyst signals → proposes trades → runs risk checks |
| Execute Approved | Every 1 min | Sends approved trades to Alpaca for execution |
| Auto-Execute | Every 1 min | Auto-approves high-confidence proposals (if `AUTO_EXECUTE=true`) |
| Sync Portfolio | Every 5 min | Pulls latest portfolio/position data from Alpaca |
| Check Stop-Losses | Every 1 min | Monitors positions for stop-loss / take-profit triggers |

### Always-On Tasks (Run 24/7)

| Task | Frequency | What It Does |
|------|-----------|-------------|
| Collect News | Every 30 min | Fetches financial news from Finnhub for all watchlist stocks |
| Collect Economic | Daily at 8 AM | Updates macroeconomic indicators from FRED (GDP, CPI, rates, etc.) |
| Collect Filings | Every 6 hours | Checks SEC EDGAR for new 10-K/10-Q filings |
| Analyze News | Every 15 min | Sends unanalyzed news to Claude for sentiment scoring |
| Analyze Filings | Every 1 hour | Sends new filings to Claude for financial analysis |
| Context Synthesis | Every 2 hours | Claude combines all data sources into a holistic per-stock assessment |

### Weekly / Periodic Tasks

| Task | Frequency | What It Does |
|------|-----------|-------------|
| Retrain Models | Sunday 2 AM | Retrains XGBoost/LightGBM on newest data. Auto-promotes new model only if it outperforms the current one. |
| AI Stock Discovery | Tue/Thu 7 AM | Claude analyzes economic data, watchlist performance, and user hints to recommend stocks to add/remove from the watchlist |

### After-Hours Tasks

| Task | Frequency | What It Does |
|------|-----------|-------------|
| Collect Daily Bars | Mon–Fri 5 PM | Downloads full daily OHLCV bars after market close |

---

## 9. Development Mode

The `docker-compose.override.yml` is automatically applied when you run `docker compose up` and enables development features:

| Feature | What It Does |
|---------|-------------|
| **Hot-reload (backend)** | FastAPI restarts on Python file changes (via `--reload` flag) |
| **Hot-reload (frontend)** | Next.js dev server with instant refresh (`npx next dev`) |
| **Volume mounts** | Backend and frontend code mounted from host → edit files locally, changes apply instantly |
| **Debug logging** | Celery worker runs with `--loglevel=debug` |
| **Direct API access** | Frontend port 3000 exposed, backend port 8000 accessible at `http://localhost:8000` |

```bash
# Development (hot-reload, debug logs)
docker compose up

# Production (optimized builds, no hot-reload)
docker compose -f docker-compose.yml up -d
```

> In production, explicitly specify only `docker-compose.yml` to skip the override file.

---

## 10. Going Live (Paper → Real Money)

**Do NOT do this until you've run paper trading for weeks/months and are satisfied with performance.**

### Pre-Flight Checklist

- [ ] Paper trading has been running for at least 4+ weeks
- [ ] You've reviewed analytics (win rate, Sharpe, drawdown) and they're acceptable
- [ ] You've reviewed Claude's trade reasoning and it makes sense to you
- [ ] `AUTO_EXECUTE` has been tested in paper mode
- [ ] All circuit breakers (daily loss limit, max drawdown) have been tuned
- [ ] You have funded your Alpaca live brokerage account

### Steps

1. **Get live API keys** from Alpaca:
   - Go to [app.alpaca.markets](https://app.alpaca.markets) → **Live Trading** → **API Keys**
   - Generate new keys (these are separate from paper trading keys)

2. **Update `.env`:**
   ```
   TRADING_MODE=live
   ALPACA_API_KEY=<live-key>
   ALPACA_SECRET_KEY=<live-secret>
   ALPACA_BASE_URL=https://api.alpaca.markets
   ```

3. **Consider tightening risk limits:**
   ```
   RISK_MAX_TRADE_DOLLARS=500
   RISK_DAILY_LOSS_LIMIT=250
   RISK_MIN_CONFIDENCE=0.75
   AUTO_EXECUTE=false          # Keep manual approval initially
   ```

4. **Restart the platform:**
   ```bash
   docker compose down
   docker compose up -d
   ```

### Live Mode Safety Features

The platform automatically applies extra protections in live mode:

| Feature | Paper Mode | Live Mode |
|---------|-----------|-----------|
| Max trade size | As configured | 50% of configured limit |
| Daily loss halt | As configured | 50% of configured limit |
| Min confidence | As configured | At least 0.75 (even if config is lower) |
| Execution delay | None | 5-second delay before order placement |
| Alert severity | Info | Warning |

---

## 11. Monitoring & Maintenance

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f scheduler

# Last 100 lines
docker compose logs --tail 100 worker
```

### Health Check

```bash
curl https://localhost/api/health
# Returns: {"status":"ok","trading_mode":"paper","database":"ok","redis":"ok"}
```

The dashboard also shows system status (online/offline, trading paused/halted) in real-time.

### Alerts

The platform pushes real-time alerts via WebSocket to the browser (bell icon in the sidebar). Alert types:

| Alert Type | Severity | Trigger |
|-----------|----------|--------|
| `trade_executed` | Info (paper) / Warning (live) | A trade was executed |
| `circuit_breaker` | Critical | Trading halted by risk manager |
| `model_retrained` | Info | ML model retrain completed |
| `stock_discovery` | Info | AI watchlist discovery completed (stocks added/removed) |
| `system_error` | Critical | Trade execution failed |

### Backups

**What to back up:** The PostgreSQL database volume (`pgdata`) contains all your data.

```bash
# Backup database to a SQL dump
docker compose exec postgres pg_dump -U trader trader > backup_$(date +%Y%m%d).sql

# Restore from dump
docker compose exec -T postgres psql -U trader trader < backup_20260408.sql
```

### Updating

```bash
git pull
docker compose build
docker compose down
docker compose up -d
docker compose exec api alembic upgrade head   # if there are new migrations
```

### Restarting

```bash
# Restart everything
docker compose restart

# Restart a single service
docker compose restart worker

# Full shutdown and start
docker compose down
docker compose up -d
```

---

## 12. Cost Estimates

### Monthly Running Costs

| Service | Cost | Notes |
|---------|------|-------|
| **Anthropic (Claude)** | ~$80–120/mo | Largest cost. Depends on watchlist size & task frequency. 10 stocks with default intervals. Includes 2 discovery cycles/week (~$0.10 each). |
| **Alpaca** | $0 | Free for paper and basic live trading |
| **Finnhub** | $0 | Free tier (60 calls/min) |
| **FRED** | $0 | Free, unlimited |
| **SEC EDGAR** | $0 | Free |
| **Hardware** | $0–30/mo | $0 if running on existing hardware. ~$5–30/mo for a VPS. |
| **Domain + DNS** | $0–12/yr | Optional. Only if you want external HTTPS access. |

**Total: ~$80–130/month** (almost entirely Anthropic API costs)

### Reducing Anthropic Costs

If the Claude bill is too high, reduce the frequency of AI analysis tasks in `.env`:

```
ANALYZE_NEWS_INTERVAL_SEC=3600       # Every 1 hour instead of 15 min
ANALYZE_FILINGS_INTERVAL_SEC=7200    # Every 2 hours instead of 1 hour
CONTEXT_SYNTHESIS_INTERVAL_SEC=14400 # Every 4 hours instead of 2 hours
DECISION_CYCLE_INTERVAL_SEC=3600     # Every 1 hour instead of 30 min
```

This can reduce the Claude bill to ~$30–50/month at the cost of less frequent analysis.

---

## 13. Troubleshooting

### Container won't start

```bash
# Check what failed
docker compose ps
docker compose logs <service-name>
```

**Common causes:**
- Missing `.env` values → fill in all required keys
- Port already in use → stop other services on ports 80/443
- Docker not running → start Docker Desktop

### Database connection error

```bash
# Check PostgreSQL is healthy
docker compose exec postgres pg_isready -U trader

# Check migrations are applied
docker compose exec api alembic current
```

### Celery tasks not running

```bash
# Check worker is processing
docker compose logs -f worker

# Check scheduler is sending tasks
docker compose logs -f scheduler

# Manually trigger a task (from the web UI)
# Dashboard → Collection Status → click "Trigger" on any task
```

### Frontend shows "API error"

- Check the API is running: `curl http://localhost:8000/api/health`
- Check Caddy is routing correctly: `docker compose logs caddy`
- In development mode, ensure `NEXT_PUBLIC_API_URL=http://localhost:8000`

### Claude analysis returning errors

- Verify `ANTHROPIC_API_KEY` is set and valid
- Check you have billing enabled in the Anthropic console
- Check the worker logs: `docker compose logs worker | grep -i anthropic`

### "Trading halted" message

This means a circuit breaker tripped (daily loss limit or max drawdown exceeded):
1. Go to the web UI → Config page
2. Review the halt reason
3. Click **Resume Trading** after reviewing
4. Or via CLI: `curl -X POST https://localhost/api/risk/resume`
