# RL Training Architecture — Explained

## How Text Becomes Numbers (The Core Question)

A neural network / RL agent can only consume numeric inputs. **Claude's text never goes directly into the RL model.** Here's the pipeline:

```
Raw Text (news articles, SEC filings)
    ↓
Claude analyzes it (runs BEFORE training data is captured)
    ↓
Claude outputs NUMERIC SCORES:
    - sentiment_score: float (-1.0 to 1.0)
    - sentiment_magnitude: float (0 to 1)
    - material_event: binary (0 or 1)
    - synthesis_sentiment: float (-1.0 to 1.0)
    - synthesis_confidence: float (0 to 1)
    ↓
These numbers go into the state vector alongside price data
    ↓
RL agent sees ONLY numbers — never text
```

Claude acts as a **feature extractor** — it reads qualitative information (earnings call language, SEC filing tone, news sentiment) and distills it into a handful of numeric signals. By the time the RL agent sees the data, everything is a float in a vector. This is a well-established pattern: use a domain-expert preprocessor (Claude) to compress unstructured data into structured features, then feed those features to a model that operates purely on numbers.

The same applies to the ML (XGBoost) signals — they produce `ml_prediction_encoded` (-1/0/1 for sell/hold/buy) and `ml_confidence` (0-1). Just numbers.

## The State Vector (What the RL Agent "Sees")

Each timestep (trading day), the agent receives one flat numeric vector:

| Section | Features | Source |
|---------|----------|--------|
| **Portfolio state** | 20 | Cash %, position count, exposure, drawdown, sector weights, recent returns, Sharpe |
| **Market state** | 15 | VIX level + trend + percentile, SPY vs moving averages, fed funds rate, yield curve, CPI, unemployment, day-of-week, month encoding |
| **Per-stock** (x18) | 50 each | Price ratios, technical indicators (RSI, MACD, Bollinger, etc.), ML signal + confidence, Claude sentiment + magnitude, synthesis score, analyst conviction, position info |

**Total: 35 + (18 x 50) = 935 features** — all floats, all normalized to reasonable ranges.

## The Training Loop

```
for each episode (= one pass through historical data):
    reset simulated portfolio to $100K cash
    
    for each trading day:
        1. Observe state vector (935 floats)
        2. Agent outputs actions: one of {hold, buy_small, buy_large, sell_half, sell_all} per stock
        3. Simulate trades with transaction costs
        4. Advance to next day, update portfolio with new prices
        5. Compute reward = daily_return - drawdown_penalty - turnover_penalty
        6. Agent learns: "this state + these actions → this reward"
    
    repeat 1000s of episodes, agent improves its policy
```

The RL algorithm (PPO/SAC) learns a **policy network** — a neural net that maps state vectors to action probabilities. Over many episodes, it discovers patterns like "when RSI is oversold AND Claude sentiment just turned positive AND VIX is falling → buying works well."

## What You're Actually Collecting vs. What You Need

Here's the gap analysis (as of April 13, 2026):

| Data Type | Status | In DB? | Coverage | Issue |
|-----------|--------|--------|----------|-------|
| **Daily prices (OHLCV)** | Collecting | 27K bars from 2021 | 1306 trading days | Good — this is the backbone |
| **Technical indicators** | Not stored | Computed on-the-fly | N/A | Not a problem — recomputed from prices at training time |
| **ML signals** | Just started | 30 rows | ~0 days | Fixed April 13 (model file was lost on deploy); will accumulate going forward |
| **News sentiment** | Collecting | 860 rows | 6 trading days | Only started April 4 — needs time |
| **Context synthesis** | Collecting | 322 rows | 1 trading day | Only started April 11 — needs time |
| **Economic indicators** | Collecting | 80 rows from 2023 | Good | Covers GDP, CPI, rates, VIX etc. |
| **Portfolio snapshots** | **NOT collecting** | 0 rows | None | **GAP** — no portfolio state history |
| **Trade history** | None yet | 0 rows | None | Expected — no trades in data_collection mode |

### Critical Gaps

1. **Portfolio snapshots (0 rows)** — The RL agent needs to know its own portfolio state (cash, positions, drawdown) at each timestep. For initial training on historical data, you can simulate this (the environment tracks a virtual portfolio). But for online/continued training with real data, you need the `sync_portfolio` task running and storing snapshots. Currently it's scheduled but has `last_run: null` — likely because there are no real positions yet.

2. **Sentiment/synthesis coverage is thin** — Only 6-10 days of data. The plan's minimum target is 63 trading days. You need ~3 months of accumulation before you have enough non-price signal coverage.

3. **No snapshot assembly** — The original plan had dedicated `rl_state_snapshots` and `rl_stock_snapshots` tables that would capture the complete state vector daily at market close. Those tables were created then **dropped** (migration 0016). The current approach is to reconstruct state vectors from source tables at training time. This works but means the training pipeline needs to do the assembly.

### What's NOT a Gap

- **Prices going back to 2021** — Plenty for the price/technical portion of the state vector
- **Economic data from 2023** — Good macro coverage
- **Technical indicators** — Don't need to be stored; they're recomputed from prices by `feature_engineering.py`

## How Training Will Actually Work

Given that you have 5 years of price data but only days of sentiment/synthesis:

**Phase 1 — Price-Only Training (possible now):**
The RL environment can be trained with just price + technical + economic data. The sentiment/synthesis/ML-signal features would be zero-filled. This gives the agent a baseline policy that understands market structure and risk management. Not ideal, but functional.

**Phase 2 — Full-Feature Training (after ~3 months of collection):**
Once you have 63+ trading days of all signal types, the training data includes the full state vector. The agent can learn correlations between Claude's sentiment shifts, ML signal changes, and price movements.

**The training pipeline:**
1. Export data from server via `/api/training/*` endpoints
2. On your GTX 5070 TI training PC, the `rl_environment.py` assembles state vectors from the exported data
3. `train_rl_agent.py` runs PPO/SAC for ~1M timesteps
4. Export trained model to ONNX format
5. Upload ONNX to server, activate it, switch to trading mode

## What Should Change Now

The collection pipeline is **mostly aligned**. The main thing to ensure:

1. **ML signals are accumulating** — Fixed today, confirmed working
2. **Sentiment + synthesis keep running** — They are, checked Celery tasks
3. **Portfolio sync should start** — Even with no positions, it should record the empty state (cash=1000, no positions) daily so the training data has portfolio context
4. **Time** — You need weeks/months of continuous collection for the non-price features to build up meaningful coverage

The existing `rl_environment.py` and `train_rl_agent.py` are already built and match the architecture. The training API endpoints serve the raw data. The missing piece is just accumulating enough days of signal data.
