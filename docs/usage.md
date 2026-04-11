# Trading Platform — Pipeline Usage Guide

The platform operates as a 5-stage pipeline. Each stage feeds into the next.

---

## Stage 1: DISCOVER — Find Stocks to Watch

| Task | Schedule | Description |
|------|----------|-------------|
| `discover_stocks` | Tue & Thu 7:00 AM | Runs 4 screening strategies (market movers, earnings catalysts, peer expansion, curated sector scan), enriches candidates via Finnhub, then asks Claude to pick the best additions/removals for the watchlist. |

**Populates:** `stocks` (watchlist), `discovery_log`

---

## Stage 2: COLLECT — Gather Raw Data

| Task | Schedule | Description |
|------|----------|-------------|
| `collect_prices` | Every 1 min (market hours) | Pulls latest intraday price quotes from Alpaca for all watchlist stocks. |
| `collect_daily_bars` | Weekdays 5:00 PM | Pulls end-of-day OHLCV bars from Alpaca for all watchlist stocks. |
| `backfill_historical_prices` | Manual | Pulls 5 years of historical daily bars per stock. Needed before ML training. |
| `collect_news` | Every 30 min | Pulls latest news articles from Finnhub for each watchlist stock. |
| `collect_filings` | Daily 6:00 AM | Pulls recent 10-K, 10-Q, and 8-K SEC filings from EDGAR for watchlist stocks. |
| `collect_economic_data` | Daily 7:00 AM | Pulls macroeconomic indicators (GDP, CPI, unemployment, etc.) from FRED. |

**Populates:** `prices`, `news_articles`, `sec_filings`, `economic_indicators`

---

## Stage 3: ANALYZE — Score and Interpret Data

| Task | Schedule | Description |
|------|----------|-------------|
| `analyze_news_sentiment` | Every 15 min | Claude reads unanalyzed news articles and scores each for sentiment (bullish/bearish/neutral) with a confidence score and summary. |
| `analyze_filings` | Daily 8:00 AM | Claude reads SEC filings and extracts key risks, opportunities, financial highlights, and an overall sentiment score. |
| `run_context_synthesis` | Every 2 hours | Claude combines all available signals (news sentiment, filing analysis, economic data, price action) into a single holistic analysis per stock with a conviction score. |

**Populates:** `news_analyses`, `filing_analyses`, `context_syntheses`

---

## Stage 4: SIGNALS & DECISIONS — Generate Trade Ideas

| Task | Schedule | Description |
|------|----------|-------------|
| `generate_ml_signals` | Every 30 min (market hours) | Runs XGBoost/LightGBM models on price features to produce a directional signal (long/short/neutral) with probability per stock. |
| `retrain_model` | Sunday 2:00 AM | Retrains the ML models on the latest price and feature data. Requires substantial price history from backfill. |
| `run_decision_cycle` | Every 30 min (market hours) | The core decision engine. Combines ML signals + context synthesis + economic data + risk state to generate concrete trade proposals (buy/sell/hold with size and reasoning). |

**Populates:** `ml_signals`, `model_registry`, `proposed_trades`

---

## Stage 5: EXECUTION — Place and Manage Trades

| Task | Schedule | Description |
|------|----------|-------------|
| `execute_approved_trades` | Every 5 min (market hours) | Sends approved trade proposals to Alpaca paper trading API. |
| `auto_execute_proposals` | Every 10 min (market hours) | When `AUTONOMOUS_MODE=true`, auto-approves proposals that meet confidence thresholds. |
| `check_stop_losses` | Every 2 min (market hours) | Monitors open positions against stop-loss levels and triggers exits. |
| `sync_portfolio` | Every 15 min (market hours) | Syncs local portfolio state with Alpaca's actual positions and balances. |

**Populates:** `trades`, `portfolio_positions`, `portfolio_snapshots`

---

## Recommended Manual Run Order

When starting fresh with a populated watchlist:

1. **`collect_daily_bars`** — get price history for watchlist stocks
2. **`collect_news`** — pull recent news (if not already collected)
3. **`collect_filings`** — pull SEC filings from EDGAR
4. **`collect_economic_data`** — pull macro indicators (if not already collected)
5. **`analyze_news_sentiment`** — have Claude score the news
6. **`analyze_filings`** — have Claude analyze the filings
7. **`run_context_synthesis`** — combine everything into per-stock analysis
8. **`backfill_historical_prices`** — pull 5 years of data (slow, needed for ML)
9. **`retrain_model`** — train ML models on historical data
10. **`generate_ml_signals`** — produce ML signals
11. **`run_decision_cycle`** — generate trade proposals

Once the pipeline has run end-to-end, the scheduled tasks keep everything updated automatically.