# Plan: Personal AI Trading System Architecture Document

## Core Vision

A fully automated, 24/7 AI-driven stock trading platform that:
- Researches, analyzes, and trades autonomously around the clock
- Ingests business news, economic trends, sector context, and historical patterns
- Accepts personal analyst insights as a first-class input signal
- Runs entirely self-hosted on a home network (Ubuntu PC)
- Uses Docker Compose for full portability between hardware
- Provides a modern web interface (Next.js + Tailwind/shadcn) for monitoring, control, and analyst input

---

## Concept Assessment

**Your core concept is sound.** The multi-signal approach (news + economic trends + business context + personal analysis → AI → autonomous trading with rules) mirrors how institutional quantitative trading systems work. Separating "learning from history" from "acting on current state" is the right decomposition.

**One important reframing:** You don't need (or want) a single "custom trained model." What you actually want is an **ensemble of specialized components**, each excellent at one thing:

- **No single model can handle all data types.** News text, price time-series, macro-economic indicators, and SEC filings are fundamentally different data types. They need different approaches.
- **LLMs (Claude) are great for NLP** (parsing news, sentiment, summarizing filings, reasoning about context) but poor at pure time-series prediction.
- **Classical ML (XGBoost/LightGBM) actually outperforms deep learning** for tabular financial prediction tasks — this is well-documented in ML benchmarks.
- **Claude API as the reasoning backbone** — for news analysis, sentiment extraction, synthesizing multi-source context, and acting as the "strategic brain" that weighs all signals. No local LLM hosting needed for NLP tasks.

---

## Critical Analysis: Should You Train/Fine-Tune Models?

### The Short Answer: **It depends on what kind of model and what for.**

There are three distinct questions here, and they have different answers:

### 1. Training a Custom LLM or Fine-Tuning an LLM for Financial Analysis?
**Verdict: No. Not worth it.**

- Fine-tuning an LLM (even with LoRA) on financial data requires curating tens of thousands of high-quality labeled examples (news article → market impact). This is months of data engineering work.
- Claude is already excellent at financial text analysis, sentiment extraction, and reasoning about business context. Prompt engineering with Claude API will get you 90%+ of what a fine-tuned model would give you, at a fraction of the effort.
- Your GTX 5070 TI (16GB VRAM) *could* fine-tune a 7-8B parameter model with QLoRA, but the marginal improvement over well-prompted Claude for financial NLP is not worth the investment.
- **Recommendation:** Use Claude API with carefully crafted system prompts and structured output schemas. Save your GPU for the models that actually benefit from training (see below).

### 2. Training Classical ML Models (XGBoost/LightGBM) on Technical Indicators?
**Verdict: Yes. This is the sweet spot.**

- These models excel at learning patterns in tabular/numerical data (price, volume, moving averages, RSI, MACD, etc.)
- Training is fast (minutes, not hours) and doesn't need a GPU at all — CPU is fine
- You can backtest rigorously on historical data to validate before going live
- Retraining frequently (weekly/monthly) on recent data helps the model adapt to changing market regimes
- **This is where "training on historical data" genuinely adds value**
- **Recommendation:** Train XGBoost/LightGBM models on technical indicators. Retrain regularly. Backtest extensively.

### 3. Training a Deep Learning Model (LSTM/Transformer) for Price Prediction?
**Verdict: Proceed with caution. Optional and risky.**

- Time-series deep learning models *can* capture patterns that classical ML misses, but they are prone to overfitting on financial data
- Financial markets are non-stationary — patterns that worked historically may not persist
- Your GTX 5070 TI is well-suited for training these (CUDA, 16GB VRAM is plenty for small Transformers)
- **If you do this:** treat it as one signal among many, never the sole decision-maker. Use walk-forward validation, not simple train/test splits.
- **Recommendation:** Start without this. Add it later as an experimental signal once the rest of the system is working. The classical ML models + Claude reasoning will carry you far.

### Summary: The Optimal Training Strategy

| Component | Train? | Why? | Hardware |
|-----------|--------|------|----------|
| Financial NLP / Sentiment | **No** — use Claude API | Claude is already excellent; fine-tuning ROI is poor | N/A |
| Technical Signal Models | **Yes** — XGBoost/LightGBM | Sweet spot: fast to train, backtestable, proven effective | CPU only |
| Price Pattern Recognition | **Optional** — LSTM/Transformer | Can add alpha but high overfitting risk | GTX 5070 TI |
| Decision Synthesis | **No** — use Claude API | Reasoning over multiple signals is what LLMs excel at | N/A |

**Bottom line:** Your instinct to use AI for trading is correct. But "training a model" is only the right move for the technical/numerical signal generation layer (XGBoost). For everything involving language, reasoning, and context synthesis, Claude API with good prompting is the superior approach — less work, better results, and you're not maintaining training pipelines.

---

## System Architecture

### Layer 1: Data Collection Pipeline (24/7 Autonomous)
- **Market Data** — Alpaca API (real-time + historical OHLCV, free with account)
- **News & Sentiment** — Finnhub (company news, earnings calendar), SEC EDGAR (corporate filings, free)
- **Economic Indicators** — FRED API (free, Federal Reserve economic data — GDP, unemployment, CPI, interest rates)
- **Sector/Industry Data** — Finnhub industry metrics, custom RSS feeds for vertical-specific news
- **Scheduler** — Celery Beat + Redis for periodic collection jobs (every minute for prices, hourly for news, daily for economic data)
- **Storage** — PostgreSQL for structured data (prices, indicators, signals), with TimescaleDB extension for efficient time-series queries

### Layer 2: AI/ML Signal Generation (Ensemble)

#### A. Technical Signal Models (TRAINED LOCALLY — this is where training matters)
- **XGBoost/LightGBM classifiers** trained on 100+ technical indicators (RSI, MACD, Bollinger, volume profiles, etc.) + historical price patterns
- **Training approach:** Walk-forward validation on 5-10 years of historical data. Retrain weekly/monthly.
- **Output:** Buy/sell/hold probability scores per stock
- **Training hardware:** CPU is sufficient (fast — minutes per model). GPU not needed here.

#### B. Claude-Powered Analysis Engine (NOT TRAINED — prompt-engineered)
- **News Sentiment Analysis** — Claude API processes news articles, extracts sentiment, identifies material events, rates impact severity
- **Earnings & Filings Analysis** — Claude reads 10-K/10-Q/8-K filings from SEC EDGAR, extracts key metrics, flags anomalies
- **Multi-Source Context Synthesis** — Claude combines news + economic state + sector trends + your personal notes into a structured assessment
- **Strategic Reasoning** — Claude acts as the "senior analyst" that weighs qualitative factors no numerical model can capture
- **Output:** Structured JSON with sentiment scores, risk flags, opportunity assessments, reasoning chains

#### C. Pattern Recognition (OPTIONAL — trained on GTX 5070 TI)
- Lightweight Transformer or LSTM for time-series regime detection (bull/bear/sideways classification)
- Trained on historical price data using the separate training PC
- Treat as one signal among many — never the sole decision-maker
- Add this after the core system is proven

#### D. Personal Analyst Input (via Web UI)
- Structured forms for entering stock thesis, conviction level (1-10), time horizon, catalyst triggers
- Free-text notes that Claude incorporates into its analysis context
- Override flags (e.g., "avoid this stock regardless of signals", "increase confidence in this sector")

### Layer 3: Decision Engine
- **Signal Aggregator** — combines all signal sources with configurable, per-stock weights
- **Claude as Decision Synthesizer** — takes all signals + your personal analyst input and produces a final trade recommendation with reasoning
- **Position Sizing** — Kelly criterion or fixed fractional, configurable per strategy
- **Output:** Ordered list of trade actions with confidence scores and full reasoning chains (auditable)

### Layer 4: Risk Management (HARD-CODED — AI cannot override)
- Max $ per trade (absolute cap)
- Max % of portfolio per position
- Max % of portfolio per sector
- Daily loss limit (circuit breaker — halts ALL trading if hit)
- Max drawdown from peak (circuit breaker)
- Minimum confidence threshold to execute
- Restricted hours / market conditions rules
- **These are enforced in code, not by AI reasoning. The AI proposes, risk management disposes.**

### Layer 5: Execution Engine
- **Broker Integration** — Alpaca API (paper trading first, then live)
- **Order Types** — market, limit, stop-loss, trailing stop, bracket orders
- **Execution Logging** — every order with full context: what signals triggered it, Claude's reasoning, confidence score, risk check results
- **Slippage Tracking** — compare expected vs. actual fill prices
- **24/7 Operation** — runs as Docker service with health checks and auto-restart

### Layer 6: Web Interface (Next.js + Tailwind + shadcn/ui)
- **Dashboard** — portfolio value, P&L (daily/weekly/monthly/all-time), active positions, recent trades, system health
- **Signal Viewer** — what each model/source is saying for each stock, with Claude's reasoning chains
- **Analyst Workbench** — enter personal analysis, thesis notes, conviction scores, override flags
- **Configuration** — adjust signal weights, risk parameters, watchlist management, strategy settings
- **Backtesting Console** — run strategies against historical data, view performance metrics, compare approaches
- **Trade Journal** — full audit trail with decision rationale for every trade
- **Manual Override** — force buy/sell, pause/resume trading, emergency stop
- **Alerts & Notifications** — configurable alerts via the web UI (and optionally email/webhook)

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Frontend** | Next.js 14+ / React / Tailwind CSS / shadcn/ui | Modern, fast, great DX |
| **Backend API** | Python 3.11+ / FastAPI / SQLAlchemy / Alembic | Best ML ecosystem |
| **Database** | PostgreSQL 16 + TimescaleDB extension | Time-series optimized |
| **Cache / Queue** | Redis + Celery | Task scheduling, caching |
| **AI/LLM** | Claude API (Anthropic) | Reasoning, NLP, synthesis |
| **ML Models** | XGBoost, LightGBM, scikit-learn | Technical signal models |
| **Optional DL** | PyTorch (trained on GTX 5070 TI) | Pattern recognition |
| **Backtesting** | vectorbt or backtrader | Strategy validation |
| **Broker** | Alpaca API | Paper + live trading |
| **Containerization** | Docker Compose | Full stack orchestration |
| **Reverse Proxy** | Caddy | Automatic HTTPS, routing |
| **Monitoring** | Prometheus + Grafana (optional) | System health |

### Docker Compose Services
```yaml
services:
  frontend:        # Next.js app
  api:             # FastAPI backend
  worker:          # Celery workers (data collection, signal generation)
  scheduler:       # Celery Beat (cron-like job scheduling)
  postgres:        # PostgreSQL + TimescaleDB
  redis:           # Cache + message broker
  caddy:           # Reverse proxy + automatic HTTPS
```

### Training PC (Separate — GTX 5070 TI)
- Used for: training XGBoost/LightGBM models, optional deep learning experiments
- Trained models exported as artifacts (pickle/ONNX files)
- Copied to the trading server (or shared via NFS/SMB on home network)
- Not part of the 24/7 runtime — training is an offline batch process

---

## Backtesting & Historical Data Strategy

1. **Data Acquisition** — download 5-10 years of daily OHLCV data via Alpaca/Polygon free historical APIs. Store in PostgreSQL/TimescaleDB.
2. **Walk-Forward Validation** — train on rolling windows (e.g., train on 3 years, test on next 6 months, slide forward). This prevents look-ahead bias.
3. **Backtesting Framework** — use `vectorbt` (fast, vectorized) or `backtrader` (more features). Run strategies against historical data with realistic assumptions (slippage, commissions).
4. **Paper Trading Validation** — after backtest looks good, run live paper trading for 1-3 months minimum before real money.
5. **Performance Metrics** — Sharpe ratio, max drawdown, win rate, profit factor, Calmar ratio. Compare against buy-and-hold S&P 500 as baseline.

---

## External API Cost Estimates

### Required APIs

| Service | What For | Free Tier | Paid Tier | Recommended |
|---------|----------|-----------|-----------|-------------|
| **Alpaca** | Market data + trade execution | Free (5 API calls/min, 15-min delayed) | $99/mo (unlimited, real-time) | Start free (paper trading), upgrade for live |
| **Claude API (Anthropic)** | News analysis, sentiment, reasoning, decision synthesis | N/A | ~$50-150/mo (estimate based on usage) | Required — core reasoning engine |
| **Finnhub** | Company news, earnings calendar, economic events | Free (60 calls/min) | $50/mo (300 calls/min) | Start free, upgrade if rate-limited |
| **FRED API** | Economic indicators (GDP, CPI, rates, unemployment) | **Free** (unlimited) | N/A | Free — no reason not to use |
| **SEC EDGAR** | Corporate filings (10-K, 10-Q, 8-K) | **Free** (10 req/sec) | N/A | Free — no reason not to use |

### Claude API Cost Breakdown (Estimated)

Assuming Claude 3.5 Sonnet pricing (~$3/M input, ~$15/M output tokens):

| Task | Frequency | Est. Tokens/Call | Monthly Cost |
|------|-----------|-----------------|-------------|
| News sentiment analysis | ~200 articles/day | ~2K input + 500 output | ~$45/mo |
| Earnings/filing analysis | ~20 filings/week | ~10K input + 2K output | ~$15/mo |
| Decision synthesis | ~50 decisions/day | ~5K input + 1K output | ~$30/mo |
| Context reasoning (ad-hoc) | ~20/day | ~3K input + 1K output | ~$10/mo |
| **Claude Total** | | | **~$80-120/mo** |

*Note: Actual costs depend heavily on how many stocks you're tracking and how frequently Claude is consulted. Tracking 10-20 stocks with hourly analysis puts you in this range. Caching and batching can reduce costs significantly.*

### Monthly Cost Summary

| Phase | Services | Est. Monthly Cost |
|-------|----------|-------------------|
| **Phase 1: Paper Trading** | Alpaca (free) + Finnhub (free) + FRED (free) + EDGAR (free) + Claude API | **$80-120/mo** |
| **Phase 2: Live Trading (small)** | Alpaca ($99/mo for real-time) + Finnhub (free) + Claude API | **$180-220/mo** |
| **Phase 3: Expanded** | Alpaca ($99/mo) + Finnhub ($50/mo) + Polygon ($29-200/mo for better historical data) + Claude API | **$260-470/mo** |

### Cost Optimization Tips
- **Cache aggressively** — don't re-analyze the same news article twice. Store Claude's analysis in PostgreSQL.
- **Batch requests** — send multiple articles to Claude in one call instead of one-by-one.
- **Tiered analysis** — use cheap heuristics (keyword matching) to filter which articles are worth sending to Claude.
- **Use Haiku/smaller models** for simple tasks (basic sentiment yes/no) and Sonnet/Opus for complex reasoning (decision synthesis).
- **FRED and SEC EDGAR are free** — lean heavily on these for economic and fundamental data.

---

## Phased Implementation Roadmap

### Phase 1: Foundation & Paper Trading (Months 1-3)
1. Set up Docker Compose infrastructure (PostgreSQL, Redis, Caddy)
2. Build data collection pipeline (Alpaca, Finnhub, FRED, EDGAR)
3. Build Next.js web dashboard (portfolio view, basic charts)
4. Integrate Claude API for news sentiment analysis
5. Train initial XGBoost models on 5+ years of historical data
6. Build backtesting module — validate strategies against historical data
7. Connect to Alpaca paper trading
8. **Run paper trading for minimum 2-3 months before any real money**

### Phase 2: Refinement & Live Trading (Months 4-6)
1. Analyze paper trading results — identify what's working, what's not
2. Build analyst workbench (personal insight input, thesis notes)
3. Implement full risk management layer
4. Retrain models incorporating paper trading learnings
5. Start live trading with a small account ($500-2000)
6. Monitor closely — keep paper trading running in parallel for comparison

### Phase 3: Maturation (Months 6+)
1. Add optional deep learning signal (LSTM/Transformer trained on GTX 5070 TI)
2. Expand stock universe
3. Add more sophisticated position sizing
4. Build comprehensive trade journal with performance analytics
5. Iterate on Claude prompts based on real trading outcomes

---

## Relevant Files

- `plans/Trading_Services_and_APIs.md` — existing API/service research to cross-reference for data source and broker selections
- `plans/Architecture.md` — this file

---

## Verification

1. Every component runs in Docker Compose on a single Ubuntu PC (16-32GB RAM recommended)
2. Only external dependencies are APIs (Alpaca, Claude, Finnhub, FRED, EDGAR) — no cloud infrastructure
3. Full stack is portable via `docker compose up` on any machine
4. Paper trading phase precedes any real money exposure (mandatory 2-3 months minimum)
5. Risk management layer is hard-coded in the execution path — AI cannot override it
6. GTX 5070 TI training PC is separate from the 24/7 trading server — training is offline

---

## Decisions

- **Ensemble approach** — Claude API for NLP/reasoning + XGBoost for technical signals + optional deep learning for patterns. Not one monolithic model.
- **Claude API over local LLMs** — superior reasoning quality, no VRAM contention on trading server, manageable cost (~$80-120/mo)
- **XGBoost/LightGBM for technical signals** — proven effective on financial tabular data, fast to train, easy to backtest. This is where "training" genuinely adds value.
- **Don't fine-tune an LLM** — Claude with prompt engineering beats a LoRA fine-tune for financial NLP at this scale. The ROI on fine-tuning is poor.
- **Next.js + Tailwind + shadcn/ui** — modern, responsive, great component library. No Streamlit — you want a real app.
- **Alpaca as starting broker** — free, purpose-built for algo trading, excellent paper trading, clean API
- **Docker Compose for everything** — portable, reproducible, easy to move between machines
- **Python backend + TypeScript frontend** — Python for ML/trading (best ecosystem), TypeScript/React for the web UI (your preference)
- **Backtesting before live trading is non-negotiable** — validate everything on historical data first

---

## Risks & Limitations

1. **Overfitting** — the #1 killer of algorithmic trading systems. Models that look great on historical data fail in live markets. Mitigation: walk-forward validation, paper trading, conservative position sizing.
2. **Survivorship bias** — historical datasets typically only include stocks that still exist. Companies that went bankrupt are missing, making backtests look better than reality.
3. **Market regime changes** — patterns that worked in 2020-2024 may not work in 2026+. Mitigation: retrain frequently, monitor model drift, have circuit breakers.
4. **Claude API dependency** — if Anthropic has an outage, your reasoning engine is offline. Mitigation: graceful degradation (system pauses new trades, holds existing positions).
5. **Latency** — this is not a high-frequency trading system. Claude API calls add 1-5 seconds. Fine for swing/position trading, not suitable for scalping.
6. **Costs can grow** — if you expand to tracking 100+ stocks with frequent Claude calls, API costs could increase significantly. Monitor and optimize.
7. **Regulatory** — automated trading with your own money is legal, but be aware of pattern day trader rules ($25k minimum for frequent day trading) and wash sale rules for taxes.
