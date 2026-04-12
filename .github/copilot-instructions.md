> **Auto-generated project context.** Refresh by running '/project-context' in chat.

# AI Trader

AI-driven autonomous stock trading platform. Combines ML models (XGBoost/LightGBM), Claude AI analysis (sentiment, filings, synthesis), and human analyst input into an ensemble signal system. Hard-coded risk management layer prevents AI from overriding safety checks. Supports paper and live trading via Alpaca API. Web dashboard for monitoring, configuration, and trade approval.

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Runtime | Python | ≥3.11 |
| API Framework | FastAPI | ≥0.115 |
| ORM | SQLAlchemy (async) | ≥2.0 |
| DB Driver | asyncpg | ≥0.30 |
| Migrations | Alembic | ≥1.13 |
| Validation | Pydantic | ≥2.7 |
| Task Queue | Celery + Redis | ≥5.4 |
| Database | PostgreSQL 16 + TimescaleDB | — |
| AI/LLM | Anthropic SDK (Claude) | ≥0.39 |
| ML | XGBoost, LightGBM, scikit-learn | — |
| Broker API | alpaca-py | ≥0.28 |
| HTTP Client | httpx | ≥0.27 |
| Frontend | Next.js (App Router) | ^14.2 |
| UI | React + Tailwind CSS + shadcn/ui | ^18.3 / ^3.4 |
| Charts | Recharts | ^2.12 |
| Language (FE) | TypeScript (strict) | ^5.5 |
| Containerization | Docker Compose | — |

## Project Structure

```
backend/
  app/
    config.py                  — Pydantic settings (env vars, trading params)
    main.py                    — FastAPI app setup, route registration, CORS
    database.py                — SQLAlchemy async engine + session
    celery_app.py              — Celery config, Beat schedule definitions
    dynamic_scheduler.py       — Runtime schedule override support
    api/                       — 15 FastAPI route files (50+ endpoints)
    models/                    — 20+ SQLAlchemy ORM models
    engine/                    — Decision engine, executor, risk manager, position sizer
    analysis/                  — Claude NLP: sentiment, filings, context synthesis
    collectors/                — Data ingestion (Alpaca, Finnhub, FRED, SEC EDGAR)
    ml/                        — Feature engineering, XGBoost/LightGBM inference
    tasks/                     — Celery task definitions (20+ tasks)
  alembic/versions/            — 14 schema migrations
frontend/src/
  app/                         — 12 pages (overview, stocks, trades, signals, watchlist, etc.)
  components/                  — sidebar, alert-bell, ui/ (button, card)
  lib/                         — api.ts (fetch wrapper), utils.ts
plans/                         — Architecture.md, Implementation_Plan.md, etc.
scripts/                       — backup/restore, deploy, seed, training scripts
```

## API Routes (backend/app/api/)

| File | Prefix | Description |
|------|--------|-------------|
| stocks.py | /api/stocks | Stock CRUD, watchlist, search |
| trades.py | /api/trades | Proposed trades, approve/reject, decision cycle |
| portfolio.py | /api/portfolio | Positions, P&L, trade history, snapshots |
| analysis.py | /api/analysis | Claude analysis results, synthesis, token usage |
| ml.py | /api/ml, /api/backtest | ML signals, model registry, backtesting |
| risk.py | /api/risk | Risk state, limits, weights, pause/resume |
| analyst.py | /api/analyst | Analyst thesis, conviction, catalysts, overrides |
| discovery.py | /api/discovery | AI stock discovery, hints, decisions |
| alerts.py | /api/alerts | Alert list, acknowledge, WebSocket stream |
| collection.py | /api/collection | Collector status, manual trigger |
| economic.py | /api/economic-indicators | FRED data (GDP, CPI, rates) |
| analytics.py | /api/analytics | Performance metrics, Sharpe, drawdown |
| system.py | /api/system | System config, settings |
| status.py | /api/status | Health check, task status, system flags |
| tasks.py | /api/tasks | Celery task queue, trigger, results |

## Architecture

- **6-Layer Pipeline**: Data Collection → AI/ML Signal Generation → Decision Engine → Risk Management → Execution → Dashboard
- **Ensemble Signals**: ML (30%) + Claude NLP (40%) + Analyst Input (30%) — weights configurable
- **Hard-Coded Risk Layer**: Max $/trade, max %/position, max %/sector, daily loss limit, max drawdown, min confidence — AI cannot override
- **Claude Models**: Haiku (fast, cheap — sentiment) + Sonnet (smart — filing analysis, synthesis, decisions)
- **Decision Engine**: Aggregates all signals → Claude synthesizes → position sizing → risk check → propose trade
- **Trade Approval**: Proposed → Queued → Approved/Rejected → Executed (manual or auto-execute mode)
- **Celery Beat Scheduling**: Market-hours-aware task scheduling with dynamic overrides
- **Docker Compose Stack**: PostgreSQL+TimescaleDB, Redis (AOF persistence), FastAPI, Celery worker+beat, Next.js

## Key Domain Concepts

- **ProposedTrade**: AI-generated trade recommendation with full reasoning chain, confidence score, and risk check results
- **ContextSynthesis**: Per-stock holistic assessment combining all signal sources
- **RiskState**: Singleton row tracking circuit breakers, trading halts, and current risk limits
- **AnalystInput**: Human thesis with conviction (1-10), catalysts, and override flags (none/avoid/boost)
- **Growth Mode**: Auto-reinvest profits with configurable position sizing
- **Stock Discovery**: AI evaluates market conditions and user hints to manage watchlist

## Coding Standards

- Python 3.11+, type hints on all function signatures
- Pydantic models for all API request/response validation
- SQLAlchemy async sessions, no raw SQL outside Alembic migrations
- Celery tasks are thin wrappers calling service/engine functions
- `pydantic-settings` for configuration (env vars with defaults)
- Frontend: TypeScript strict, Next.js App Router, `@/*` path alias
- All dates UTC, convert to local at display layer only
- Docker Compose for all services — never run services directly on host

## Build Progress

Core platform built. All layers functional. Paper trading active.

| Area | Status | Scope |
|------|--------|-------|
| Data Collection | ✅ | Alpaca, Finnhub, FRED, SEC EDGAR collectors |
| AI/NLP Analysis | ✅ | Sentiment, filing analysis, context synthesis |
| ML Signals | ✅ | XGBoost/LightGBM training, inference, backtesting |
| Decision Engine | ✅ | Signal aggregation, Claude decisioning, position sizing |
| Risk Management | ✅ | Hard-coded limits, circuit breakers, trading halts |
| Execution Engine | ✅ | Alpaca order placement, fills, slippage tracking |
| Web Dashboard | ✅ | 12 pages — overview, stocks, trades, signals, config, etc. |
| Task Scheduling | ✅ | Celery Beat with market-hours awareness |
| Alerts | ✅ | Real-time alerts with WebSocket streaming |
| Stock Discovery | ✅ | AI-driven watchlist management |
| Database | ✅ | 14 Alembic migrations, 20+ models |
