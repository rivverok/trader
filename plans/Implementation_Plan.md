# Implementation Plan: AI Trading Platform

> Reference: `plans/Architecture.md` for system design rationale and cost estimates.
> Reference: `plans/Trading_Services_and_APIs.md` for API/service research.

---

## Pre-Implementation: Account Setup & API Keys

Before writing any code, create accounts and obtain API keys for all external services. Every key goes into `.env` (see `.env.example` at the root of the project).

### Required Accounts

| Service | URL | What to Do | Key(s) You'll Get | Cost |
|---------|-----|------------|-------------------|------|
| **Alpaca** | https://alpaca.markets | 1. Sign up for free account. 2. Go to "Paper Trading" → API Keys. 3. Generate key + secret. | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Free |
| **Anthropic (Claude)** | https://console.anthropic.com | 1. Sign up. 2. Add payment method. 3. Go to API Keys → Create Key. | `ANTHROPIC_API_KEY` | Pay-per-use (~$80-120/mo) |
| **Finnhub** | https://finnhub.io | 1. Sign up for free account. 2. Dashboard → API Token (auto-generated). | `FINNHUB_API_KEY` | Free tier (60 calls/min) |
| **FRED** | https://fred.stlouisfed.org/docs/api/api_key.html | 1. Create FRED account. 2. Request API key (instant approval). | `FRED_API_KEY` | Free (unlimited) |
| **SEC EDGAR** | https://www.sec.gov/os/accessing-edgar-data | No key needed. Set a User-Agent header with your name and email (SEC requirement). | `SEC_EDGAR_USER_AGENT` (your email) | Free |

### Alpaca: Paper vs Live

- Paper trading base URL: `https://paper-api.alpaca.markets`
- Live trading base URL: `https://api.alpaca.markets`
- **Use paper trading for all of Stages 1–5. Do NOT switch to live until Stage 6.**
- Paper and live use different API key pairs. Generate paper keys first.

---

## Project Structure

```
trader/
├── plans/                          # Architecture docs (already exists)
├── docker-compose.yml              # All services
├── docker-compose.override.yml     # Local dev overrides
├── .env.example                    # Template for environment variables
├── .env                            # Actual secrets (gitignored)
├── caddy/
│   └── Caddyfile                    # Reverse proxy config (auto-HTTPS)
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml              # Python dependencies (Poetry or pip)
│   ├── alembic/                    # Database migrations
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry point
│   │   ├── config.py               # Settings from .env
│   │   ├── database.py             # SQLAlchemy engine + session
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── stock.py
│   │   │   ├── price.py
│   │   │   ├── news.py
│   │   │   ├── signal.py
│   │   │   ├── trade.py
│   │   │   ├── portfolio.py
│   │   │   └── analyst_input.py
│   │   ├── api/                    # FastAPI route handlers
│   │   │   ├── stocks.py
│   │   │   ├── signals.py
│   │   │   ├── trades.py
│   │   │   ├── portfolio.py
│   │   │   ├── analyst.py
│   │   │   ├── backtest.py
│   │   │   └── config.py
│   │   ├── collectors/             # Data ingestion modules
│   │   │   ├── alpaca_collector.py
│   │   │   ├── finnhub_collector.py
│   │   │   ├── fred_collector.py
│   │   │   ├── edgar_collector.py
│   │   │   └── base.py
│   │   ├── analysis/               # Claude-powered analysis
│   │   │   ├── sentiment.py
│   │   │   ├── filings.py
│   │   │   ├── context_synthesis.py
│   │   │   └── prompts/            # System prompts for Claude
│   │   │       ├── sentiment.txt
│   │   │       ├── filings.txt
│   │   │       └── decision.txt
│   │   ├── ml/                     # Trained ML models
│   │   │   ├── technical_signals.py
│   │   │   ├── feature_engineering.py
│   │   │   ├── training.py
│   │   │   └── models/             # Serialized model files (.joblib)
│   │   ├── engine/                 # Decision + execution
│   │   │   ├── decision_engine.py
│   │   │   ├── risk_manager.py
│   │   │   ├── position_sizer.py
│   │   │   └── executor.py
│   │   ├── tasks/                  # Celery task definitions
│   │   │   ├── collection_tasks.py
│   │   │   ├── analysis_tasks.py
│   │   │   ├── trading_tasks.py
│   │   │   └── maintenance_tasks.py
│   │   └── utils/
│   │       ├── logging.py
│   │       └── indicators.py       # Technical indicator calculations
│   └── tests/
│       ├── test_collectors.py
│       ├── test_analysis.py
│       ├── test_ml.py
│       ├── test_engine.py
│       ├── test_risk.py
│       └── test_api.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── components.json             # shadcn/ui config
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx            # Dashboard
│   │   │   ├── signals/page.tsx
│   │   │   ├── analyst/page.tsx
│   │   │   ├── trades/page.tsx
│   │   │   ├── backtest/page.tsx
│   │   │   ├── config/page.tsx
│   │   │   └── api/                # Next.js API routes (proxy to backend)
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn/ui components
│   │   │   ├── dashboard/
│   │   │   ├── signals/
│   │   │   ├── analyst/
│   │   │   ├── trades/
│   │   │   └── charts/
│   │   ├── lib/
│   │   │   ├── api.ts              # Backend API client
│   │   │   └── utils.ts
│   │   └── hooks/
│   │       └── use-portfolio.ts
│   └── public/
└── training/                       # Runs on GTX 5070 TI PC (not in Docker)
    ├── requirements.txt
    ├── train_technical_model.py
    ├── train_deep_learning.py      # Optional — Stage 7
    ├── backtest_strategies.py
    ├── feature_engineering.py
    └── data/                       # Downloaded historical data
```

---

## Stage 1: Infrastructure Foundation

**Goal:** Docker Compose stack with PostgreSQL, Redis, FastAPI, Next.js, and Caddy all running. Database migrations working. API serves health check. Frontend renders a shell dashboard. Everything is containerized and starts with one command.

### What to Build

1. **`docker-compose.yml`** — all 7 services (postgres, redis, api, worker, scheduler, frontend, caddy)
2. **PostgreSQL + TimescaleDB** — container with volume mount, initialized with TimescaleDB extension
3. **Redis** — container with persistence enabled
4. **FastAPI backend (`backend/`)** —
   - `app/main.py` — FastAPI app with CORS, health check endpoint (`GET /api/health`)
   - `app/config.py` — Pydantic Settings loading all `.env` variables
   - `app/database.py` — SQLAlchemy async engine, session factory, connection pool
   - `Dockerfile` — Python 3.11, installs deps, runs uvicorn
   - `pyproject.toml` — all Python dependencies (fastapi, uvicorn, sqlalchemy, alembic, celery, redis, anthropic, alpaca-py, xgboost, lightgbm, scikit-learn, pandas, numpy, ta-lib, vectorbt, httpx, pydantic)
5. **Alembic** — initialized, connected to PostgreSQL, first migration creates empty schema
6. **Next.js frontend (`frontend/`)** —
   - `npx create-next-app` with TypeScript, Tailwind, App Router
   - Install and configure shadcn/ui
   - `src/app/page.tsx` — shell dashboard page with sidebar nav (Dashboard, Signals, Analyst, Trades, Backtest, Config)
   - `src/lib/api.ts` — typed API client that hits the backend through Caddy
   - `Dockerfile` — Node 20, builds Next.js, runs in production mode
7. **Caddy** — reverse proxy routing `/` → frontend, `/api` → backend. Caddy handles HTTPS automatically (self-signed for `localhost`, or real certs via Let's Encrypt if you add a domain). Caddyfile is ~10 lines.

### Deployment Commands (Ubuntu Server)

```bash
# ── 1. System prerequisites ──
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git curl

# Add your user to docker group (log out and back in after)
sudo usermod -aG docker $USER

# ── 2. Clone / set up project ──
cd /home/$USER
git clone <your-repo-url> trader    # or mkdir trader && cd trader
cd trader

# ── 3. Create .env from template ──
cp .env.example .env
nano .env    # Fill in all API keys and secrets

# ── 4. TLS — Caddy handles this automatically ──
# No manual cert generation needed!
# Caddy auto-provisions self-signed certs for localhost/IP access.
# If you later add a domain (e.g., trader.yourdomain.com), Caddy
# will auto-provision a real Let's Encrypt cert — zero config.

# ── 5. Build and start everything ──
docker compose build
docker compose up -d

# ── 6. Run database migrations ──
docker compose exec api alembic upgrade head

# ── 7. Verify ──
curl -k https://localhost/api/health    # Should return {"status": "ok", ...}
# Open https://<server-ip> in browser — should see the shell dashboard
```

### Stage 1 Verification Checklist

- [ ] `docker compose up -d` starts all 7 containers without errors
- [ ] `docker compose ps` shows all services as "running" / "healthy"
- [ ] `GET https://localhost/api/health` returns JSON with status "ok", database connection "ok", redis connection "ok"
- [ ] PostgreSQL has TimescaleDB extension enabled (`SELECT extname FROM pg_extension` returns `timescaledb`)
- [ ] Alembic migrations run without errors
- [ ] `https://<server-ip>` in browser shows the Next.js shell dashboard with navigation sidebar
- [ ] Frontend can call backend through Caddy (`/api/health` fetch from browser works)
- [ ] Containers auto-restart after `docker compose restart`
- [ ] Data persists after `docker compose down && docker compose up -d` (PostgreSQL volume)

**Do not proceed to Stage 2 until every checkbox passes.**

---

## Stage 2: Data Collection Pipeline

**Goal:** System autonomously collects and stores market prices, news, economic indicators, and SEC filings on a schedule. All data is queryable via API endpoints and visible on the frontend.

### What to Build

1. **Database models + migrations** —
   - `stocks` table — symbol, name, sector, industry, exchange, watchlist flag, created_at
   - `prices` table — stock_id, timestamp, open, high, low, close, volume (TimescaleDB hypertable)
   - `news_articles` table — stock_id (nullable), headline, summary, source, url, published_at, raw_content, sentiment_score (nullable), analyzed (bool)
   - `economic_indicators` table — indicator_code, name, value, date, source
   - `sec_filings` table — stock_id, filing_type, filed_date, url, raw_content, analyzed (bool)
   - Alembic migrations for all tables

2. **Collectors** —
   - `alpaca_collector.py` — fetches OHLCV bars (1-min, 5-min, 1-day) for all watchlist stocks. Supports historical backfill (bulk download of 5+ years) and live updates. Uses `alpaca-py` SDK.
   - `finnhub_collector.py` — fetches company news for watchlist stocks, earnings calendar, and company profiles. Deduplicates by URL.
   - `fred_collector.py` — fetches key economic indicators: GDP, CPI, unemployment rate, federal funds rate, 10Y treasury yield, consumer sentiment. Uses `fredapi` package.
   - `edgar_collector.py` — fetches recent 10-K, 10-Q, 8-K filings for watchlist companies via SEC EDGAR full-text search API. Stores filing metadata + raw content.
   - `base.py` — abstract base collector with error handling, retry logic (exponential backoff), rate limit respect, and logging.

3. **Celery tasks + Beat schedule** —
   - `collect_prices` — runs every 1 minute during market hours (9:30 AM – 4:00 PM ET, Mon-Fri)
   - `collect_daily_bars` — runs once at 5:00 PM ET daily (after market close)
   - `collect_news` — runs every 30 minutes
   - `collect_economic_data` — runs once daily at 8:00 AM ET
   - `collect_filings` — runs every 6 hours
   - `backfill_historical_prices` — one-time task, downloads 5+ years of daily data for all watchlist stocks

4. **API endpoints** —
   - `GET /api/stocks` — list all stocks (with watchlist filter)
   - `POST /api/stocks` — add stock to system (symbol, auto-fetches name/sector from Alpaca)
   - `GET /api/stocks/{symbol}/prices` — price history with date range + interval params
   - `GET /api/stocks/{symbol}/news` — recent news articles
   - `GET /api/economic-indicators` — latest values for all tracked indicators
   - `GET /api/collection/status` — last run time, success/fail counts for each collector

5. **Frontend pages** —
   - **Dashboard** — update to show watchlist stocks with latest price, daily change %, and sparkline chart
   - **Stock detail** — click a stock → see price chart (candlestick), news feed, key stats
   - **System status** — collection pipeline health: last run, next run, error counts

### Deployment Commands (after Stage 1)

```bash
# ── Run new migrations ──
docker compose exec api alembic upgrade head

# ── Add initial watchlist stocks ──
# Via API (through curl or the frontend):
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" \
  -d '{"symbol": "MSFT"}'
# ... add 5-10 stocks to start

# ── Trigger historical backfill ──
docker compose exec api python -m app.tasks.collection_tasks backfill

# ── Verify Celery workers are running and picking up tasks ──
docker compose logs -f worker
docker compose logs -f scheduler

# ── Check data in database ──
docker compose exec postgres psql -U trader -d trader -c "SELECT COUNT(*) FROM prices;"
docker compose exec postgres psql -U trader -d trader -c "SELECT COUNT(*) FROM news_articles;"
```

### Stage 2 Verification Checklist

- [ ] At least 5 stocks added to watchlist via API and visible on frontend dashboard
- [ ] Historical backfill completed: `prices` table has 5+ years of daily bars for each watchlist stock (verify row counts)
- [ ] Live price collection runs every minute during market hours — verify new rows appearing in `prices` table
- [ ] News articles collected and stored — `GET /api/stocks/AAPL/news` returns recent articles with headlines, sources, timestamps
- [ ] Economic indicators collected — `GET /api/economic-indicators` returns GDP, CPI, unemployment, fed funds rate, etc. with recent values
- [ ] SEC filings collected — at least one 10-K or 10-Q stored per watchlist company
- [ ] Celery Beat schedule visible in logs — tasks firing at expected intervals
- [ ] Collection errors are logged but don't crash the worker (retry with backoff)
- [ ] Rate limits respected — Finnhub free tier (60/min), EDGAR (10/sec), Alpaca (5/min on free)
- [ ] `GET /api/collection/status` shows last run times and success/fail counts
- [ ] Frontend dashboard shows live prices, daily change, and a basic price chart for each stock
- [ ] Data persists across container restarts

**Do not proceed to Stage 3 until every checkbox passes.**

---

## Stage 3: Claude-Powered Analysis Engine

**Goal:** Claude API analyzes news articles, SEC filings, and economic context. Sentiment scores and analysis are stored in the database and displayed on the frontend. Analysis runs automatically on new data.

### What to Build

1. **Claude integration layer** —
   - `analysis/sentiment.py` — sends news articles to Claude API with a structured system prompt. Extracts: sentiment (-1.0 to 1.0), impact severity (low/medium/high), material event flag, key entities, one-line summary. Output as structured JSON (Claude's tool use / JSON mode).
   - `analysis/filings.py` — sends SEC filing content to Claude. Extracts: revenue trend, margin changes, risk factor changes vs. prior filing, unusual items, forward guidance sentiment. Output as structured JSON.
   - `analysis/context_synthesis.py` — given a stock symbol, pulls latest news sentiments + economic indicators + SEC analysis + user analyst notes and sends to Claude to produce a holistic assessment. Output: overall sentiment, confidence, key factors, risks, opportunities, reasoning chain.
   - `analysis/prompts/` — well-crafted system prompts for each task. These are plain text files loaded at runtime. Version controlled so you can iterate on them.

2. **Caching & cost control** —
   - Before sending an article to Claude, check if it's already been analyzed (`analyzed = true` flag)
   - Batch up to 5 short articles into a single Claude call where possible
   - Use Claude Haiku for simple sentiment scoring (cheaper), Sonnet for filing analysis and synthesis (smarter)
   - Track token usage per call, store in a `claude_usage` table (date, task_type, input_tokens, output_tokens, cost_estimate)

3. **Database additions** —
   - `news_analyses` table — article_id, sentiment_score, impact_severity, material_event, key_entities (JSONB), summary, claude_model_used, tokens_used, created_at
   - `filing_analyses` table — filing_id, revenue_trend, margin_analysis, risk_changes, guidance_sentiment, key_findings (JSONB), claude_model_used, tokens_used, created_at
   - `context_syntheses` table — stock_id, overall_sentiment, confidence, key_factors (JSONB), risks (JSONB), opportunities (JSONB), reasoning_chain (text), created_at
   - `claude_usage` table — date, task_type, model, input_tokens, output_tokens, estimated_cost

4. **Celery tasks** —
   - `analyze_pending_news` — runs every 15 minutes, processes un-analyzed articles
   - `analyze_pending_filings` — runs every hour, processes un-analyzed filings
   - `run_context_synthesis` — runs every 2 hours for each watchlist stock
   - All tasks respect rate limits and have error handling / retry logic

5. **API endpoints** —
   - `GET /api/stocks/{symbol}/analysis` — latest context synthesis + component analyses
   - `GET /api/stocks/{symbol}/news` — update to include sentiment scores from analysis
   - `GET /api/analysis/usage` — Claude API usage and cost tracking (daily/weekly/monthly totals)

6. **Frontend** —
   - **Signal Viewer** page — for each stock: sentiment gauge, impact summary, material events timeline, Claude's reasoning chain (expandable), cost tracking
   - **Dashboard** — update stock cards to show sentiment badge (bullish/bearish/neutral) with color coding

### Stage 3 Verification Checklist

- [ ] New news articles are automatically sent to Claude for sentiment analysis within 15 minutes of collection
- [ ] `GET /api/stocks/AAPL/analysis` returns structured sentiment data with scores, impact ratings, and summaries
- [ ] SEC filing analysis produces meaningful extraction — revenue trends, risk changes, guidance
- [ ] Context synthesis combines news + economic + filings into a coherent per-stock assessment
- [ ] Claude responses are valid JSON matching the expected schema (no parse errors)
- [ ] Already-analyzed articles are NOT re-sent to Claude (caching works)
- [ ] `claude_usage` table tracks every API call with token counts
- [ ] `GET /api/analysis/usage` shows cumulative cost tracking — verify it aligns with Anthropic dashboard
- [ ] Haiku is used for simple sentiment, Sonnet for complex analysis (verify via `claude_model_used` column)
- [ ] Signal Viewer page displays sentiment data, reasoning chains, and material events per stock
- [ ] Dashboard stock cards show colored sentiment badges
- [ ] System handles Claude API errors gracefully (rate limits, timeouts) — retries without crashing
- [ ] Run for 24 hours and verify: no duplicate analyses, no runaway costs, no crashed workers

**Do not proceed to Stage 4 until every checkbox passes.**

---

## Stage 4: Technical Signal Models (ML Training & Inference)

**Goal:** XGBoost/LightGBM models trained on historical data produce buy/sell/hold signals for each watchlist stock. Backtesting framework validates model performance. Training runs on the separate GPU PC; inference runs on the trading server.

### What to Build

1. **Feature engineering (`ml/feature_engineering.py`)** —
   - Compute 100+ technical indicators from price data using `ta` or `pandas-ta` library:
     - Trend: SMA(10,20,50,200), EMA(10,20,50), MACD, ADX, Aroon, Ichimoku
     - Momentum: RSI(14), Stochastic, Williams %R, CCI, ROC
     - Volatility: Bollinger Bands, ATR, Keltner Channels, historical volatility
     - Volume: OBV, VWAP, Chaikin Money Flow, volume SMA ratio
     - Price patterns: returns (1d, 5d, 10d, 20d), high/low range, gap up/down
   - Label generation: target variable is forward return classification
     - `buy` if 5-day forward return > 2%
     - `sell` if 5-day forward return < -2%
     - `hold` otherwise
     - (Thresholds configurable)

2. **Training pipeline (`training/train_technical_model.py`)** — runs on GTX 5070 TI PC
   - Loads historical price data from PostgreSQL (or exported CSV)
   - Runs feature engineering
   - Walk-forward validation: train on 3 years, test on next 6 months, slide 6 months, repeat
   - Trains both XGBoost and LightGBM, selects best performer
   - Outputs:
     - Serialized model file (`.joblib`)
     - Feature importance rankings
     - Validation metrics per fold (accuracy, precision, recall, F1, Sharpe of simulated trades)
     - Training report (JSON)
   - Model artifacts saved to `backend/app/ml/models/`

3. **Inference (`ml/technical_signals.py`)** — runs on trading server
   - Loads latest trained model from disk
   - Given a stock + latest price data, computes features and runs prediction
   - Output: `{"signal": "buy"|"sell"|"hold", "confidence": 0.0-1.0, "feature_importances": {...}}`

4. **Backtesting (`training/backtest_strategies.py`)** —
   - Uses `vectorbt` to simulate trading based on model signals
   - Realistic assumptions: 0.1% slippage per trade, $1 commission per trade
   - Outputs: total return, Sharpe ratio, max drawdown, win rate, profit factor, comparison vs. buy-and-hold S&P 500
   - Saves results to database + generates HTML report

5. **Database additions** —
   - `ml_signals` table — stock_id, model_name, model_version, signal, confidence, feature_importances (JSONB), created_at
   - `backtest_results` table — strategy_name, start_date, end_date, total_return, sharpe_ratio, max_drawdown, win_rate, profit_factor, trades_count, report_json (JSONB)
   - `model_registry` table — model_name, version, file_path, training_date, validation_metrics (JSONB), is_active

6. **Celery tasks** —
   - `generate_ml_signals` — runs every hour during market hours, generates signals for all watchlist stocks using latest model
   - `retrain_model` — runs weekly (Sunday night), retrains with latest data (or triggered manually)

7. **API endpoints** —
   - `GET /api/stocks/{symbol}/signals` — latest ML signal + confidence + feature importances
   - `GET /api/models` — list trained models with validation metrics
   - `POST /api/models/retrain` — trigger retraining manually
   - `GET /api/backtest/results` — list backtest runs with metrics
   - `POST /api/backtest/run` — trigger a new backtest with configurable params

8. **Frontend** —
   - **Signal Viewer** — update to show ML signal alongside Claude sentiment (side by side)
   - **Backtest Console** page — run backtests, view equity curves, performance table, drawdown chart
   - **Model Management** — list models, view training metrics, activate/deactivate

### Training PC Setup

```bash
# ── On the GTX 5070 TI PC (Ubuntu) ──

# Install CUDA toolkit (if not already)
sudo apt install -y nvidia-cuda-toolkit

# Set up Python environment
sudo apt install -y python3.11 python3.11-venv
cd /home/$USER
git clone <your-repo-url> trader
cd trader/training

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# requirements.txt: xgboost, lightgbm, scikit-learn, pandas, numpy,
#                   ta, vectorbt, sqlalchemy, psycopg2-binary, joblib, matplotlib

# Connect to PostgreSQL on the trading server
# Edit .env with the trading server's IP:
# DATABASE_URL=postgresql://trader:password@<trading-server-ip>:5432/trader
# (PostgreSQL must expose port 5432 — see docker-compose.yml ports section)

# ── Run training ──
python train_technical_model.py --symbols AAPL,MSFT,GOOGL --years 5

# ── Run backtest ──
python backtest_strategies.py --model models/xgboost_v1.joblib --start 2021-01-01 --end 2025-12-31

# ── Copy trained model to trading server ──
scp models/xgboost_v1.joblib user@<trading-server-ip>:/home/user/trader/backend/app/ml/models/
# Or use a shared NFS mount between the two PCs
```

### Stage 4 Verification Checklist

- [ ] Feature engineering produces 100+ features per stock per day without NaN errors (forward-fill gaps)
- [ ] Training completes on historical data (5+ years) in under 30 minutes
- [ ] Walk-forward validation produces at least 5 out-of-sample test folds
- [ ] Model achieves better-than-random accuracy on out-of-sample folds (> 35% for 3-class; compare to 33% baseline)
- [ ] Backtest shows the strategy doesn't just buy-and-hold (has actual trades, stop-losses trigger)
- [ ] Backtest metrics include: Sharpe > 0 on out-of-sample, max drawdown < 30%, profit factor > 1.0
- [ ] Trained model file (`.joblib`) loads successfully on the trading server
- [ ] `generate_ml_signals` task produces signals for all watchlist stocks every hour
- [ ] `GET /api/stocks/AAPL/signals` returns signal, confidence, and top feature importances
- [ ] Signal Viewer shows ML predictions alongside Claude analysis for each stock
- [ ] Backtest Console allows running backtests from the web UI with configurable parameters
- [ ] Model Registry shows trained models with their validation metrics
- [ ] Retraining can be triggered from the UI and produces a new model version

**Do not proceed to Stage 5 until every checkbox passes.**

---

## Stage 5: Decision Engine & Risk Management

**Goal:** All signals (ML, Claude analysis, personal analyst input) are combined into trade decisions. Risk management enforces hard limits. System can propose trades and explain its reasoning — but does not yet execute them.

### What to Build

1. **Analyst workbench (`api/analyst.py` + frontend)** —
   - `POST /api/analyst/input` — submit analyst input: stock_id, thesis (text), conviction (1-10), time_horizon (days), catalysts (text), override_flag (avoid/boost/none)
   - `GET /api/analyst/inputs` — list all active analyst inputs
   - `PUT /api/analyst/input/{id}` — update an existing input
   - `DELETE /api/analyst/input/{id}` — remove an input
   - `analyst_inputs` table — stock_id, thesis, conviction, time_horizon, catalysts, override_flag, is_active, created_at, updated_at
   - Frontend: Analyst Workbench page with forms for each stock, list of active inputs, edit/delete

2. **Signal aggregation (`engine/decision_engine.py`)** —
   - For each watchlist stock, gather:
     - ML signal + confidence (from `ml_signals`)
     - Claude sentiment analysis + context synthesis (from `context_syntheses`)
     - Analyst input if any (from `analyst_inputs`)
     - Current position if any (from portfolio)
   - Combine into a single weighted score:
     - ML signal weight (configurable, default 0.3)
     - Claude sentiment weight (configurable, default 0.4)
     - Analyst conviction weight (configurable, default 0.3)
   - Override rules: if analyst says "avoid", signal is forced to SELL/HOLD regardless

3. **Claude decision synthesis** —
   - After aggregation, send the combined signal package to Claude with the decision system prompt
   - Claude produces: final recommendation (strong_buy/buy/hold/sell/strong_sell), confidence (0-1), reasoning chain, risk factors, suggested order type and price target
   - This is the "senior analyst review" — Claude can agree or disagree with the numbers and explain why

4. **Position sizing (`engine/position_sizer.py`)** —
   - Fixed fractional: risk X% of portfolio per trade (configurable, default 2%)
   - Kelly criterion (optional): size based on win probability and payoff ratio from backtest metrics
   - Output: number of shares to buy/sell, dollar amount

5. **Risk management (`engine/risk_manager.py`)** — HARD-CODED, not configurable by AI —
   - `check_trade_allowed(proposed_trade) -> (bool, reason)` — returns True/False with explanation
   - Checks:
     - Max $ per trade (from config, e.g., $1000)
     - Max % of portfolio per position (from config, e.g., 10%)
     - Max % of portfolio per sector (from config, e.g., 25%)
     - Daily realized loss limit (e.g., $500/day — halt if exceeded)
     - Max drawdown from portfolio peak (e.g., 15% — halt ALL trading)
     - Minimum confidence threshold (e.g., 0.6)
     - Market hours check (only trade during regular hours unless configured otherwise)
   - Risk parameters stored in `risk_config` table, editable via API/UI but NOT by AI
   - When a circuit breaker triggers, it sets a `trading_halted` flag and logs the reason
   - `trading_halted` can only be cleared by the user via the web UI

6. **Trade proposal pipeline** —
   - `proposed_trades` table — stock_id, action (buy/sell), shares, price_target, order_type, ml_signal_id, synthesis_id, analyst_input_id, risk_check_passed, risk_check_reason, confidence, reasoning_chain, status (proposed/approved/rejected/executed), created_at
   - Every trade proposal is logged with full context: which signals led to it, Claude's reasoning, risk check results
   - In this stage, trades are PROPOSED ONLY — they show up on the UI but are NOT executed automatically

7. **Celery tasks** —
   - `run_decision_cycle` — runs every 30 minutes during market hours: aggregates signals → Claude synthesis → position sizing → risk check → propose trades

8. **API endpoints** —
   - `GET /api/trades/proposed` — list proposed trades with full reasoning
   - `POST /api/trades/{id}/approve` — manually approve a proposed trade (for Stage 5 testing)
   - `POST /api/trades/{id}/reject` — reject with reason
   - `GET /api/risk/status` — current risk state (daily loss, drawdown, halted flag)
   - `PUT /api/risk/config` — update risk parameters
   - `POST /api/risk/resume` — clear `trading_halted` flag (user action only)
   - `GET /api/config/weights` — current signal weights
   - `PUT /api/config/weights` — update signal weights

9. **Frontend** —
   - **Analyst Workbench** — form to enter stock thesis, conviction, catalysts, override flags. List of active inputs.
   - **Trade Proposals** — table of proposed trades with: stock, action, shares, confidence, reasoning (expandable), risk check result, approve/reject buttons
   - **Risk Dashboard** — current drawdown gauge, daily loss tracker, position exposure by stock and sector, circuit breaker status, resume button
   - **Configuration** — signal weight sliders, risk parameter editor, watchlist management

### Stage 5 Verification Checklist

- [ ] Analyst input can be created, viewed, updated, and deleted via the web UI
- [ ] Decision cycle runs every 30 minutes and produces trade proposals
- [ ] Each trade proposal includes: ML signal, Claude analysis, analyst input (if any), combined score, reasoning chain
- [ ] Claude decision synthesis produces structured JSON with recommendation, confidence, and reasoning
- [ ] Risk manager correctly blocks trades that violate limits:
  - [ ] Trade exceeding max $ is rejected with reason
  - [ ] Trade exceeding max position % is rejected with reason
  - [ ] Trade exceeding sector % is rejected with reason
  - [ ] Daily loss circuit breaker triggers and halts trading (test by manually recording losses)
  - [ ] Drawdown circuit breaker triggers and halts trading
  - [ ] Trades below confidence threshold are rejected
- [ ] `trading_halted` flag can only be cleared via the web UI (not by the decision engine)
- [ ] Proposed trades are visible on the frontend with full reasoning chains
- [ ] Approve/reject buttons work — status updates correctly
- [ ] Signal weights are adjustable via the UI and affect the next decision cycle
- [ ] Risk parameters are adjustable via the UI
- [ ] Run a full decision cycle manually and trace through the logs: data collection → analysis → ML signal → Claude synthesis → risk check → proposal
- [ ] System handles missing data gracefully (e.g., no news for a stock → uses only ML + analyst input)

**Do not proceed to Stage 6 until every checkbox passes.**

---

## Stage 6: Execution Engine (Paper Trading)

**Goal:** System automatically executes approved trades via Alpaca paper trading API. Orders are placed, tracked, and logged. Portfolio state is kept in sync.

### What to Build

1. **Executor (`engine/executor.py`)** —
   - `execute_trade(proposed_trade) -> executed_trade` — places order via Alpaca API
   - Supports order types: market, limit (at Claude's suggested price), stop-loss (ATR-based), bracket orders (entry + stop + take-profit)
   - After order fills: update `proposed_trades` status to "executed", record fill price, fill time, commission
   - Handle partial fills, rejections, and cancellations

2. **Portfolio sync** —
   - `portfolio` table — stock_id, shares, avg_cost_basis, current_value, unrealized_pnl, realized_pnl
   - `trades` table — stock_id, action, shares, price, order_type, fill_price, fill_time, slippage, commission, proposed_trade_id, alpaca_order_id, created_at
   - Sync portfolio state from Alpaca API every 5 minutes (source of truth is Alpaca, local DB is cache)
   - Calculate P&L (daily, cumulative), slippage (expected vs fill), and portfolio metrics

3. **Auto-execution mode** —
   - `system_config` table — `auto_execute` flag (default: false in this stage)
   - When `auto_execute = true`: if a proposed trade passes risk checks and confidence > threshold, execute immediately without manual approval
   - When `auto_execute = false`: trades are proposed and require manual approval via UI (what we had in Stage 5)
   - **Start Stage 6 with auto_execute = false. Test manually. Then enable auto for paper trading.**

4. **Stop-loss and take-profit management** —
   - When a position is opened, automatically place:
     - Stop-loss order at -X% (configurable, default 5%)
     - Take-profit order at +Y% (configurable, default 10%)
   - Track these as linked orders — if one fills, cancel the other
   - Claude can suggest custom stop/take-profit levels in its recommendation

5. **Celery tasks** —
   - `execute_approved_trades` — runs every 1 minute, executes any approved but un-executed trades
   - `sync_portfolio` — runs every 5 minutes, syncs with Alpaca
   - `check_stop_loss_orders` — runs every 1 minute, monitors stop/take-profit status

6. **API endpoints** —
   - `GET /api/portfolio` — current positions, cash, total value, P&L
   - `GET /api/portfolio/history` — daily portfolio value over time
   - `GET /api/trades` — executed trades with all metadata
   - `POST /api/trades/manual` — place a manual trade (bypass decision engine, still goes through risk check)
   - `POST /api/system/pause` — pause all trading
   - `POST /api/system/resume` — resume trading
   - `GET /api/system/status` — auto_execute flag, trading state, system health

7. **Frontend** —
   - **Dashboard** — update with real portfolio data: total value, cash, P&L chart (line), positions table, today's trades
   - **Trades** page — full trade history with: stock, action, size, entry price, fill price, slippage, P&L, reasoning link
   - **Manual trade** — form to place manual buy/sell (with risk check confirmation)
   - **System controls** — pause/resume trading, enable/disable auto-execute toggle, emergency stop button (sells all positions)

### Deployment Commands

```bash
# ── Ensure Alpaca paper trading keys are in .env ──
# ALPACA_BASE_URL=https://paper-api.alpaca.markets  (NOT live!)
# ALPACA_API_KEY=<paper-key>
# ALPACA_SECRET_KEY=<paper-secret>

# ── Rebuild and deploy ──
docker compose build api worker
docker compose up -d

# ── Run migrations ──
docker compose exec api alembic upgrade head

# ── Verify Alpaca paper connection ──
docker compose exec api python -c "
from alpaca.trading.client import TradingClient
import os
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
account = client.get_account()
print(f'Account status: {account.status}')
print(f'Buying power: {account.buying_power}')
print(f'Portfolio value: {account.portfolio_value}')
"
```

### Stage 6 Verification Checklist

- [ ] Alpaca paper trading account connects successfully (account status, buying power displayed)
- [ ] Manual trade via UI: buy 1 share of AAPL → order appears in Alpaca dashboard → fills → local DB updated
- [ ] Proposed trade approved via UI → executes on Alpaca → fill recorded in `trades` table with correct price/slippage
- [ ] Portfolio sync: positions/cash match between local DB and Alpaca API
- [ ] Stop-loss order placed automatically when position is opened
- [ ] Take-profit order placed automatically when position is opened
- [ ] P&L calculation is correct: unrealized P&L updates with price changes, realized P&L records on close
- [ ] Slippage tracking: fill price vs. expected price is recorded and visible
- [ ] Pause trading: no new trades execute while paused
- [ ] Resume trading: trades resume after unpause
- [ ] Enable `auto_execute`: decision cycle → propose → risk check → execute without manual approval
- [ ] Run in auto_execute mode for 24+ hours:
  - [ ] Trades are placed and filled
  - [ ] Risk limits are respected (test by lowering them)
  - [ ] Circuit breaker halts trading when daily loss threshold is hit
  - [ ] System recovers from Alpaca API errors (retries, doesn't crash)
- [ ] Dashboard shows real-time portfolio value, positions, and P&L chart
- [ ] Trade history shows every trade with full audit trail (signals, reasoning, risk check)
- [ ] **Run paper trading for a minimum of 2-3 months before considering live trading**

**Do not proceed to Stage 7 until paper trading has run successfully for at least 2 months with positive or break-even results.**

---

## Stage 7: Advanced Features & Live Trading Preparation

**Goal:** Add remaining advanced features. Prepare for live trading. This stage runs in parallel with continued paper trading.

### What to Build

1. **Trade Journal & Analytics** —
   - `GET /api/analytics/performance` — Sharpe ratio, max drawdown, win rate, profit factor, Calmar ratio, calculated from actual trade history
   - `GET /api/analytics/attribution` — which signal source (ML, Claude, analyst) contributed most to winning vs. losing trades
   - Frontend: Performance Analytics page with equity curve, drawdown chart, monthly returns heatmap, signal attribution breakdown

2. **Model retraining pipeline improvements** —
   - Include paper trading outcomes as training data (did our prediction lead to profit or loss?)
   - Compare model versions: new retrained model vs. current model backtest performance
   - Auto-promote new model only if it outperforms on out-of-sample data

3. **Alerting system** —
   - WebSocket push to frontend for: trades executed, circuit breaker triggered, model retrained, system errors
   - Optional email alerts via SMTP (configurable in .env)
   - `alerts` table — type, severity, message, acknowledged (bool), created_at
   - Frontend: alert bell icon in header with dropdown, alerts settings page

4. **Optional: Deep learning signal (GTX 5070 TI)** —
   - Train LSTM or small Transformer on historical price sequences
   - Walk-forward validation with same rigor as XGBoost
   - Export model (ONNX or TorchScript), deploy alongside XGBoost
   - Add as a third signal source in decision engine with configurable weight (start at 0.1)
   - **Only add if XGBoost + Claude are already profitable in paper trading**

5. **Live trading toggle** —
   - Add `TRADING_MODE=paper|live` to config
   - When set to `live`:
     - Use live Alpaca API keys + base URL
     - Enable additional confirmation step: every trade requires a 5-second delay before execution (cancelable)
     - Lower all risk limits by 50% compared to paper trading initial values
     - Send alert on every trade execution

### Switching to Live Trading

```bash
# ── ONLY after 2+ months of successful paper trading ──

# 1. Generate live API keys from Alpaca dashboard
#    https://app.alpaca.markets → Live Trading → API Keys

# 2. Update .env
#    ALPACA_BASE_URL=https://api.alpaca.markets
#    ALPACA_API_KEY=<live-key>
#    ALPACA_SECRET_KEY=<live-secret>
#    TRADING_MODE=live

# 3. Fund your Alpaca brokerage account (minimum recommended: $2,000)

# 4. Restart with live config
docker compose down
docker compose up -d

# 5. Verify account
docker compose exec api python -c "
from app.config import settings
print(f'Trading mode: {settings.TRADING_MODE}')
print(f'Base URL: {settings.ALPACA_BASE_URL}')
"
# Should show "live" and the live API URL

# 6. Start with auto_execute OFF — manually approve first few live trades
# 7. Monitor closely for the first week
# 8. Gradually enable auto_execute once confident
```

### Stage 7 Verification Checklist

- [ ] Performance analytics page shows accurate metrics from paper trading history
- [ ] Signal attribution identifies which signal sources are driving profitable vs. unprofitable trades
- [ ] Alerts fire in real-time for trades, circuit breakers, and errors
- [ ] Model retraining incorporates paper trading outcomes
- [ ] (Optional) Deep learning signal is added with low weight and doesn't degrade performance
- [ ] Live trading mode changes API URLs and key references correctly
- [ ] Live mode has stricter risk limits than paper trading
- [ ] 5-second execution delay works in live mode (trade can be canceled during delay)
- [ ] Paper trading ran for 2+ months with documented results

---

## Ongoing Maintenance

After the system is live, these tasks should be performed regularly:

| Task | Frequency | How |
|------|-----------|-----|
| Review trade journal | Daily | Web UI → Trades page |
| Check system health | Daily | Web UI → Dashboard (system status) |
| Review Claude API costs | Weekly | Web UI → Analysis → Usage tracking |
| Retrain XGBoost model | Weekly/Monthly | Auto (Celery) or manual via UI |
| Update watchlist | As needed | Web UI → Config → Watchlist |
| Update analyst inputs | As needed | Web UI → Analyst Workbench |
| Review risk parameters | Monthly | Web UI → Config → Risk Management |
| Update Docker images | Monthly | `docker compose pull && docker compose up -d` |
| Backup database | Weekly | `docker compose exec postgres pg_dump -U trader trader > backup.sql` |
| Review and improve Claude prompts | Monthly | Edit files in `backend/app/analysis/prompts/` |
| Check API deprecations | Quarterly | Visit Alpaca, Finnhub, Anthropic changelogs |

### Database Backup Script

```bash
# Add to crontab: crontab -e
# 0 3 * * 0 /home/$USER/trader/scripts/backup.sh

#!/bin/bash
BACKUP_DIR="/home/$USER/trader/backups"
mkdir -p "$BACKUP_DIR"
FILENAME="trader_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose -f /home/$USER/trader/docker-compose.yml exec -T postgres \
  pg_dump -U trader trader | gzip > "$BACKUP_DIR/$FILENAME"
# Keep last 8 weeks of backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +56 -delete
echo "Backup complete: $FILENAME"
```

---

## Deployment Quick Reference

### First-Time Setup (Full)

```bash
# 1. Prerequisites
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git curl nano

sudo usermod -aG docker $USER
# Log out and back in

# 2. Project
git clone <repo-url> ~/trader && cd ~/trader
cp .env.example .env
nano .env    # Fill in ALL keys

# 3. TLS — handled automatically by Caddy, no manual steps needed

# 4. Build & launch
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head

# 5. Add watchlist stocks
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" -d '{"symbol":"AAPL"}'
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" -d '{"symbol":"MSFT"}'
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" -d '{"symbol":"GOOGL"}'
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" -d '{"symbol":"AMZN"}'
curl -k -X POST https://localhost/api/stocks -H "Content-Type: application/json" -d '{"symbol":"NVDA"}'

# 6. Historical backfill
docker compose exec api python -m app.tasks.collection_tasks backfill

# 7. Access UI
echo "Open https://$(hostname -I | awk '{print $1}') in your browser"
```

### Daily Operations

```bash
# Check status
docker compose ps
docker compose logs --tail=50 api
docker compose logs --tail=50 worker

# Restart everything
docker compose restart

# Update after code changes
git pull
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head

# Emergency stop
docker compose exec api python -c "
import httpx
httpx.post('https://localhost/api/system/pause', verify=False)
"

# Database shell
docker compose exec postgres psql -U trader -d trader

# View Celery task status
docker compose exec worker celery -A app.tasks inspect active
```

### Moving to New Hardware

```bash
# On old machine:
docker compose down
docker compose exec -T postgres pg_dump -U trader trader > full_backup.sql
# Copy entire ~/trader directory + full_backup.sql to new machine

# On new machine:
cd ~/trader
docker compose up -d postgres redis
docker compose exec -T postgres psql -U trader -d trader < full_backup.sql
docker compose up -d
docker compose exec api alembic upgrade head
```
