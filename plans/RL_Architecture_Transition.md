# Plan: RL Architecture Transition

## Summary

Transition the trading platform from a Claude-as-decision-maker architecture to an RL-agent-as-decision-maker architecture. The system retains Claude for what LLMs do well (text interpretation, sentiment analysis, qualitative synthesis) and delegates the actual trade decision to a reinforcement learning agent trained on historical state data.

This plan covers:
1. System mode infrastructure (data collection vs trading)
2. State snapshot data collection pipeline
3. Architecture cleanup (remove Claude decision path, stub RL agent)
4. Frontend updates (data collection dashboard, mode switching)
5. ONNX-based model deployment (train externally, deploy model file to server)
6. RL training environment specification (for external training system)

## Architecture Overview

```
CURRENT ARCHITECTURE (being retired):
  Data Collection -> Claude Analysis -> Claude Decision -> Trade Proposal -> Human Approval -> Execution
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                        REMOVE: LLM making optimization decisions

NEW ARCHITECTURE:
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ DATA COLLECTION MODE (Phase 1 — active immediately)                    │
  │                                                                        │
  │   Alpaca ──┐                                                           │
  │   Finnhub ─┤──> Raw Data Storage ──> Signal Generation ──> State       │
  │   FRED ────┤    (prices, news,       (ML inference,       Snapshot     │
  │   EDGAR ───┘     filings, econ)       Claude sentiment,   Storage      │
  │                                       Claude synthesis)    (daily)     │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ TRADING MODE (Phase 2 — enabled when RL model is loaded)               │
  │                                                                        │
  │   State Snapshot ──> RL Agent ──> Risk Manager ──> Execution           │
  │   (assembled        (ONNX         (hard limits     (Alpaca API)        │
  │    from latest       inference)    unchanged)                           │
  │    data)                                                               │
  │                    ┌──────────────────────────────────┐                │
  │                    │ Claude's new role:                │                │
  │                    │  - Explain WHY the RL agent       │                │
  │                    │    made this decision             │                │
  │                    │  - Human-readable reasoning       │                │
  │                    │  - NOT making the decision        │                │
  │                    └──────────────────────────────────┘                │
  └─────────────────────────────────────────────────────────────────────────┘
```

## Framework Decision: Why stable-baselines3 + ONNX (not Keras)

**Recommendation: stable-baselines3 (PyTorch) over Keras/TensorFlow**

| Factor | stable-baselines3 (PyTorch) | Keras (TensorFlow) |
|--------|----------------------------|---------------------|
| RL algorithms | PPO, DQN, SAC, TD3, A2C built-in | Must build from scratch or use tf-agents (less maintained) |
| Financial RL | FinRL library built on SB3 | No equivalent |
| ONNX export | First-class support, documented | Requires tf2onnx (extra step, occasional issues) |
| Community | Most active RL community | RL community has moved to PyTorch |
| Custom environments | Gymnasium standard, clean API | Same (Gymnasium) |
| Training flexibility | Full control over policy networks | Same |
| Server inference | ONNX Runtime (framework-agnostic) | ONNX Runtime (same) |

**Key insight:** The server never needs PyTorch or TensorFlow installed. It only needs `onnxruntime` (~50MB) to run inference on the exported model. Training happens externally on a GPU machine with the full PyTorch/SB3 stack.

**ONNX as the deployment format:**
- Framework-agnostic: train in PyTorch, inference anywhere
- Fast: optimized C++ runtime, no Python framework overhead
- Small: just the model weights + graph, not the training framework
- Versioned: model files can be stored, compared, rolled back

## System Modes

Replace the current pause/resume hierarchy with a cleaner mode system:

```
SYSTEM_MODE (new field on RiskState or SystemKV):
  "data_collection" — Collect data + generate signals + store snapshots. No trading.
  "trading"         — Full pipeline: data collection + RL inference + risk check + execution.
                      Requires a loaded RL model. Disabled until model exists.

Existing pause/resume stays for operational control WITHIN a mode:
  system_paused  — stops ALL tasks in current mode (emergency/maintenance)
  trading_paused — stops execution only (data collection continues in trading mode)
  trading_halted — circuit breaker (unchanged)
```

## What Gets Removed

The following components become dead code under the new architecture and should be removed:

### Backend Removals
| Component | File | Reason |
|-----------|------|--------|
| Claude decision calls | `decision_engine.py` → `_claude_decision()` | RL agent replaces Claude as decider |
| Trade proposal generation | `decision_engine.py` → proposal creation logic | RL agent outputs actions directly |
| Signal weight aggregation | `decision_engine.py` → `_aggregate_signals()` | RL agent learns its own weights |
| Context synthesis for decisions | `context_synthesis.py` decision portions | Signals go to state vector, not Claude |
| Auto-execute proposals | `tasks/decision_tasks.py` → auto_execute | No proposal step; RL decides + executes |
| Queued proposal re-evaluation | `tasks/decision_tasks.py` → reevaluate_queued | No queued proposals |
| Decision cycle task | `celery_app.py` → run_decision_cycle schedule | Replaced by RL inference task |
| Decision prompt | `analysis/prompts/decision.txt` | No longer used |
| Signal weight config | `config.py` → SIGNAL_WEIGHT_* | RL agent learns weights internally |
| Signal weight API | `api/risk.py` → weight endpoints | No configurable weights |

### Frontend Removals
| Component | Page | Reason |
|-----------|------|--------|
| Trade approval workflow | Trades page | RL + risk manager handle this |
| Manual trade entry | Trades page | Bypasses RL agent |
| Signal weight config | Config page | RL learns its own weights |
| Growth mode toggle | Config page | Position sizing is RL's job |
| Auto-execute toggle | Config page | Execution is automatic when RL decides |

### What Stays
| Component | Why |
|-----------|-----|
| Price collection (Alpaca) | Raw data for state vector |
| News collection (Finnhub) | Raw data for Claude sentiment |
| Filing collection (EDGAR) | Raw data for Claude analysis |
| Economic data (FRED) | State vector features |
| Claude sentiment analysis | Signal source → state vector input |
| Claude filing analysis | Signal source → state vector input |
| Claude context synthesis | Signal source → state vector input |
| ML signal generation | Signal source → state vector input |
| Risk manager (hard limits) | Safety layer — RL cannot override |
| Portfolio sync | Track positions |
| Analyst input | Human signal → state vector input |
| Analytics | Performance tracking, now feeds back to monitoring |
| Alerts system | Operational alerts |
| Stock discovery | Watchlist management (can keep Claude here) |

## Database Changes

### New Tables

**`rl_state_snapshots`** — One row per evaluation timestep

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| timestamp | TIMESTAMPTZ NOT NULL | Evaluation time (market close) |
| snapshot_type | VARCHAR(20) | `daily_close`, `event`, `manual` |
| portfolio_state | JSONB NOT NULL | Cash, equity, positions, drawdown, sector weights |
| market_state | JSONB NOT NULL | VIX, SPY, economic indicators, calendar |
| metadata | JSONB | Additional context (reason for event snapshot, etc.) |
| created_at | TIMESTAMPTZ | |

**`rl_stock_snapshots`** — One row per stock per evaluation timestep

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| snapshot_id | INTEGER FK | → rl_state_snapshots.id |
| symbol | VARCHAR(10) NOT NULL | Stock ticker |
| price_data | JSONB NOT NULL | OHLCV, VWAP, returns (1d/5d/20d/60d) |
| technical_indicators | JSONB | All 60+ indicators from feature_engineering |
| ml_signal | JSONB | Latest prediction, confidence, importances |
| sentiment | JSONB | Latest news sentiment score, magnitude, material events |
| synthesis | JSONB | Latest context synthesis score, key factors |
| analyst_input | JSONB | Conviction, override flag (null if none) |
| relative_strength | JSONB | vs SPY, vs sector ETF |

**`rl_models`** — Model registry for RL agents

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | |
| name | VARCHAR(100) | Human-readable name |
| version | VARCHAR(20) | Semantic version |
| algorithm | VARCHAR(20) | `PPO`, `DQN`, `SAC` |
| onnx_path | VARCHAR(255) | Path to .onnx file on server |
| state_spec | JSONB | Expected input schema (feature names, dimensions) |
| action_spec | JSONB | Output schema (action space definition) |
| training_metadata | JSONB | Reward function, training episodes, final metrics |
| backtest_metrics | JSONB | Sharpe, return, drawdown on held-out data |
| is_active | BOOLEAN DEFAULT FALSE | Currently deployed for inference |
| created_at | TIMESTAMPTZ | |
| activated_at | TIMESTAMPTZ | When last activated |

### Modified Tables

**`risk_state`** — Add system mode

| New Column | Type | Default | Description |
|------------|------|---------|-------------|
| system_mode | VARCHAR(20) | `data_collection` | `data_collection` or `trading` |

## State Vector Specification

The RL agent consumes a fixed-width numeric vector assembled from the state snapshot.

### Per-Stock Features (50 features per stock)

```
[0]  close_normalized          — close / close_20d_sma (mean-reversion reference)
[1]  volume_normalized         — volume / volume_20d_sma
[2]  return_1d                 — 1-day return
[3]  return_5d                 — 5-day return
[4]  return_20d                — 20-day return
[5]  return_60d                — 60-day return
[6]  sma_10_ratio              — close / SMA(10)
[7]  sma_20_ratio              — close / SMA(20)
[8]  sma_50_ratio              — close / SMA(50)
[9]  sma_200_ratio             — close / SMA(200)
[10] ema_10_ratio              — close / EMA(10)
[11] ema_20_ratio              — close / EMA(20)
[12] macd_normalized           — MACD / close (scale-invariant)
[13] macd_signal_normalized    — MACD signal / close
[14] macd_histogram_normalized — MACD histogram / close
[15] adx                       — ADX (already 0-100)
[16] rsi_14                    — RSI (already 0-100, normalize to 0-1)
[17] stochastic_k              — Stochastic K (0-100, normalize)
[18] stochastic_d              — Stochastic D (0-100, normalize)
[19] williams_r                — Williams %R (-100-0, normalize)
[20] cci                       — CCI (normalize with tanh or clip)
[21] roc_10                    — Rate of change (clip outliers)
[22] bb_pct                    — Bollinger Band % (0-1 typically)
[23] atr_pct                   — ATR / close (volatility as %)
[24] historical_vol_20         — 20-day realized volatility
[25] obv_slope                 — OBV 5-day slope (normalized)
[26] cmf                       — Chaikin Money Flow (-1 to 1)
[27] volume_sma_ratio          — volume / SMA(volume, 20)
[28] ml_confidence             — ML model confidence (0-1)
[29] ml_prediction_encoded     — buy=1, hold=0, sell=-1
[30] sentiment_score           — Claude sentiment (-1 to 1)
[31] sentiment_magnitude       — Sentiment magnitude (0-1)
[32] material_event            — Binary: material event detected
[33] synthesis_sentiment       — Claude synthesis score (-1 to 1)
[34] synthesis_confidence      — Synthesis confidence (0-1)
[35] analyst_conviction        — Analyst conviction (0-1, 0 if no input)
[36] analyst_override          — -1=avoid, 0=none, 1=boost
[37] vs_spy_20d                — Relative return vs SPY (20d)
[38] vs_sector_20d             — Relative return vs sector (20d)
[39] current_position_pct      — Current portfolio weight in this stock (0 if none)
[40] unrealized_pnl_pct        — Unrealized P&L on current position (0 if none)
[41] days_held                 — Days in current position (0 if none, normalized)
[42-49] reserved               — Padding for future features
```

### Portfolio Features (20 features, shared across all stocks)

```
[0]  cash_pct                  — Cash / total equity
[1]  num_positions_normalized  — Current positions / max_positions
[2]  total_exposure_pct        — Total position value / equity
[3]  largest_position_pct      — Largest single position weight
[4]  daily_pnl_pct             — Today's P&L as % of equity
[5]  unrealized_pnl_pct        — Total unrealized P&L %
[6]  current_drawdown          — Current drawdown from peak (0-1)
[7]  max_drawdown_30d          — Max drawdown over last 30 days
[8]  return_5d                 — Portfolio return over 5 days
[9]  return_20d                — Portfolio return over 20 days
[10] return_60d                — Portfolio return over 60 days
[11] sharpe_30d                — Rolling 30-day Sharpe ratio (clipped)
[12] win_rate_30d              — Win rate over last 30 trades (0-1)
[13] daily_loss_remaining_pct  — Remaining daily loss budget as % of limit
[14-19] sector_concentration   — Top-6 sector weights (sorted descending)
```

### Market Features (15 features, shared across all stocks)

```
[0]  vix_normalized            — VIX / 30 (normalize around historical mean)
[1]  vix_5d_change             — 5-day VIX change (normalized)
[2]  vix_percentile            — VIX percentile rank over 1 year (0-1)
[3]  spy_vs_sma50              — SPY close / SMA(50) - 1
[4]  spy_vs_sma200             — SPY close / SMA(200) - 1
[5]  spy_return_5d             — SPY 5-day return
[6]  spy_return_20d            — SPY 20-day return
[7]  fed_funds_rate            — Normalized (/ 10)
[8]  yield_curve_slope         — 10y - 2y (can be negative)
[9]  cpi_yoy                   — CPI year-over-year (/ 10)
[10] unemployment_rate         — Unemployment (/ 10)
[11] day_of_week               — 0-4 (Mon-Fri) / 4
[12] month_sin                 — sin(2*pi*month/12) (cyclical encoding)
[13] month_cos                 — cos(2*pi*month/12) (cyclical encoding)
[14] reserved                  — Padding
```

### Total State Vector

For N stocks in universe:
```
state = concat([
    portfolio_features,      # 20 features
    market_features,         # 15 features
    stock_1_features,        # 50 features
    stock_2_features,        # 50 features
    ...
    stock_N_features,        # 50 features
])
# Total: 35 + (N * 50) features
# For 30 stocks: 35 + 1500 = 1535 features
```

### Action Space

```
# Discrete (recommended to start):
# For each of N stocks: action in {0, 1, 2, 3, 4}
#   0 = strong_sell  (close position or go to 0%)
#   1 = sell         (reduce position by 50%)
#   2 = hold         (no change)
#   3 = buy          (add 2.5% portfolio weight)
#   4 = strong_buy   (add 5% portfolio weight)
#
# MultiDiscrete action space: [5, 5, 5, ..., 5]  (N stocks)
```

### Reward Function

```python
def compute_reward(equity_t, equity_t1, drawdown, actions, config):
    # Primary: daily portfolio return
    daily_return = (equity_t1 - equity_t) / equity_t
    
    # Drawdown penalty (exponential — punishes large drawdowns much more)
    dd_penalty = config.dd_weight * (drawdown ** 2) if drawdown > config.dd_threshold else 0
    
    # Transaction cost (discourages excessive trading)
    turnover = sum(1 for a in actions if a != 2)  # non-hold actions
    turnover_penalty = config.turnover_weight * turnover / len(actions)
    
    # Concentration penalty
    max_pos = max(position_weights)
    conc_penalty = config.conc_weight * max(0, max_pos - config.max_position) ** 2
    
    reward = daily_return - dd_penalty - turnover_penalty - conc_penalty
    return reward
```

## Implementation Phases

### Phase 1: System Mode + Data Collection Infrastructure

**Goal:** The system can run in `data_collection` mode, capturing daily state snapshots.

**Backend:**

1. **Alembic migration** — Add `system_mode` to `risk_state`, create `rl_state_snapshots`, `rl_stock_snapshots`, `rl_models` tables
2. **SQLAlchemy models** — `RLStateSnapshot`, `RLStockSnapshot`, `RLModel`
3. **State snapshot service** (`backend/app/engine/state_snapshots.py`):
   - `capture_daily_snapshot()` — assembles full state from all existing tables
   - Calls `feature_engineering.compute_features()` for each stock
   - Pulls latest ML signal, sentiment, synthesis, analyst input per stock
   - Computes portfolio state from positions + snapshots
   - Computes market state from economic indicators + SPY prices
   - Writes to `rl_state_snapshots` + `rl_stock_snapshots`
4. **Celery task** — `capture_daily_state_snapshot` runs at 4:05 PM ET weekdays
5. **System mode logic** — modify task dispatcher to check `system_mode`:
   - `data_collection`: run collection + analysis + ML signals + snapshot capture. Skip decision cycle, execution.
   - `trading`: run everything including RL inference (when model loaded)
6. **API endpoints**:
   - `GET /api/system/mode` — current mode
   - `PUT /api/system/mode` — switch modes (validates RL model exists for trading mode)
   - `GET /api/data-collection/status` — snapshot stats, coverage, quality
   - `GET /api/data-collection/snapshots` — paginated snapshot list
   - `POST /api/data-collection/snapshot` — trigger manual snapshot
   - `GET /api/data-collection/export` — export snapshots as Parquet download
7. **Tie into pause/resume** — `system_paused` stops snapshot capture too. Snapshot task checks `is_system_paused()` like all other tasks.

**Frontend:**

8. **Data Collection page** (`/data-collection`):
   - Total snapshots collected
   - Coverage: which stocks have data, date range, any gaps
   - Latest snapshot timestamp + age
   - Data quality: missing features, null counts
   - Collection status per data source (prices, news, filings, economic)
   - Export button (download Parquet)
   - Manual snapshot trigger button
   - Chart: snapshots over time (show gaps)
9. **Mode switcher** — global mode indicator in sidebar or top bar:
   - Shows current mode: "Data Collection" or "Trading"
   - Toggle switch (with confirmation dialog for trading mode)
   - Trading mode disabled if no RL model loaded
10. **Sidebar update** — add Data Collection page, reorganize:
    ```
    AI Trader
    ├─ Overview
    ├─ Dashboard
    ├─ Data Collection  ← NEW
    ├─ Watchlist
    ├─ Signals
    ├─ Analyst
    ├─ Trades          (shows stub message in data_collection mode)
    ├─ Analytics
    ├─ Models          (add RL model section)
    ├─ Tasks
    ├─ Config          (simplified — remove signal weights, add mode config)
    └─ Status
    ```

**Files to create:**
- `backend/app/models/rl_snapshot.py`
- `backend/app/models/rl_model.py`
- `backend/app/engine/state_snapshots.py`
- `backend/app/tasks/snapshot_tasks.py`
- `backend/app/api/data_collection.py`
- `backend/alembic/versions/0015_add_rl_tables.py`
- `frontend/src/app/data-collection/page.tsx`

**Files to modify:**
- `backend/app/models/__init__.py` — register new models
- `backend/app/models/risk.py` — add system_mode column
- `backend/app/main.py` — register data_collection router
- `backend/app/celery_app.py` — add snapshot task to schedule
- `backend/app/tasks/task_status.py` — mode-aware task gating
- `backend/app/api/system.py` — mode switching endpoints
- `frontend/src/components/sidebar.tsx` — add Data Collection, mode indicator
- `frontend/src/lib/api.ts` — add data collection API functions

---

### Phase 2: Architecture Cleanup

**Goal:** Remove Claude decision pipeline. Stub out RL agent inference path.

**Backend removals:**

1. **Decision engine overhaul** (`decision_engine.py`):
   - Remove `_claude_decision()`
   - Remove `_aggregate_signals()` (weighted scoring)
   - Remove proposal creation logic
   - Keep `_build_portfolio_context()` (useful for state snapshots)
   - The file becomes a thin wrapper: `run_decision_cycle()` → calls RL agent stub
2. **Remove decision prompt** — `analysis/prompts/decision.txt` (archive, don't delete)
3. **Remove decision cycle scheduling** from Celery Beat (replaced by RL inference task)
4. **Remove auto-execute and queued-proposal tasks**
5. **Remove signal weight config** from `config.py`

**Add RL agent stub:**

6. **RL Agent stub** (`backend/app/engine/rl_agent.py`):
   ```python
   class RLAgent:
       def __init__(self):
           self.session = None  # ONNX InferenceSession
           self.model_info = None

       def load_model(self, onnx_path: str, state_spec: dict):
           """Load ONNX model file for inference."""
           import onnxruntime as ort
           self.session = ort.InferenceSession(onnx_path)
           self.model_info = state_spec

       def predict(self, state_vector: np.ndarray) -> np.ndarray:
           """Run inference on state vector, return actions."""
           if self.session is None:
               raise RuntimeError("No RL model loaded")
           actions = self.session.run(None, {"input": state_vector})[0]
           return actions

       @property
       def is_loaded(self) -> bool:
           return self.session is not None
   ```
7. **RL inference task** (`backend/app/tasks/rl_tasks.py`):
   ```python
   # Stub — runs in trading mode only
   async def run_rl_inference():
       """Assemble current state → RL agent → actions → risk check → execute."""
       if system_mode != "trading":
           return {"status": "skipped", "reason": "not in trading mode"}
       if not rl_agent.is_loaded:
           return {"status": "skipped", "reason": "no model loaded"}
       # 1. Assemble state vector from latest data
       # 2. rl_agent.predict(state)
       # 3. Map actions to trades
       # 4. Risk check each trade
       # 5. Execute approved trades
       raise NotImplementedError("RL model not yet trained")
   ```
8. **Model management API** (`backend/app/api/models.py` or extend `ml.py`):
   - `POST /api/rl-models/upload` — upload ONNX file + metadata
   - `GET /api/rl-models` — list available models
   - `POST /api/rl-models/{id}/activate` — set as active model
   - `GET /api/rl-models/{id}/info` — model details, metrics
   - `DELETE /api/rl-models/{id}` — remove model

**Frontend updates:**

9. **Config page** — remove:
   - Signal weight sliders (ML/Claude/Analyst)
   - Growth mode toggle
   - Auto-execute toggle
10. **Config page** — add:
    - System mode selector
    - RL model info (active model name, version, metrics, loaded status)
11. **Trades page** — in data_collection mode, show message:
    "Trading is disabled. System is in data collection mode. Switch to trading mode when an RL model is loaded."
12. **Models page** — add RL models section:
    - Upload ONNX model
    - List uploaded models with backtest metrics
    - Activate/deactivate

**Files to create:**
- `backend/app/engine/rl_agent.py`
- `backend/app/tasks/rl_tasks.py`
- `backend/app/api/rl_models.py`
- `backend/app/analysis/prompts/archive/decision.txt` (moved)

**Files to modify:**
- `backend/app/engine/decision_engine.py` — gut and redirect to RL stub
- `backend/app/config.py` — remove SIGNAL_WEIGHT_*, add RL config
- `backend/app/celery_app.py` — remove decision cycle, add RL inference schedule
- `backend/app/tasks/decision_tasks.py` — remove or redirect
- `backend/app/main.py` — register rl_models router
- `frontend/src/app/config/page.tsx` — remove weights, add mode/model config
- `frontend/src/app/trades/page.tsx` — mode-aware display
- `frontend/src/app/models/page.tsx` — add RL models section

---

### Phase 3: Historical Backfill + Export Pipeline

**Goal:** Reconstruct state snapshots from all historical data. Provide export for training.

1. **Backfill script** (`scripts/backfill_snapshots.py`):
   - Query all dates where we have daily price bars
   - For each date, reconstruct the state snapshot:
     - Technical indicators: recompute from price history
     - ML signal: join by nearest timestamp (from ml_signals table)
     - Sentiment: join by nearest timestamp (from news_analyses)
     - Synthesis: join by nearest timestamp (from context_syntheses)
     - Portfolio state: from portfolio_snapshots (nearest to market close)
     - Market state: from economic_indicators + SPY prices
   - Write to rl_state_snapshots + rl_stock_snapshots tables
   - Idempotent: skip dates that already have snapshots

2. **Export utility** (`scripts/export_rl_data.py`):
   - Reads all snapshots in date range
   - Normalizes features (standard scaling, min-max for bounded)
   - Outputs:
     - `states.parquet` — per-stock features, indexed by (date, symbol)
     - `portfolio.parquet` — portfolio features, indexed by date
     - `market.parquet` — market features, indexed by date
     - `metadata.json` — feature names, normalization params, date range, stock universe
   - Includes data quality report (missing values, coverage gaps)

3. **Export via API** — `GET /api/data-collection/export` triggers export and returns download link

**Files to create:**
- `scripts/backfill_snapshots.py`
- `scripts/export_rl_data.py`

---

### Phase 4: RL Training Environment Specification

**Goal:** Document and spec the training environment so it can be built on the external training machine.

This phase produces DOCUMENTATION + a requirements spec, not server code. Training happens externally.

**Training stack (on external GPU machine):**
- Python 3.11+
- stable-baselines3 >= 2.3 (PPO, DQN, SAC implementations)
- gymnasium >= 0.29 (environment interface)
- torch >= 2.0 (SB3 backend)
- pandas, pyarrow (read exported Parquet)
- onnx, onnxruntime (export + validate)

**Environment specification** (`training/rl_environment.py` — portable, no server deps):

```python
class TradingEnvironment(gymnasium.Env):
    """
    Offline RL environment that replays historical state snapshots.
    
    observation_space: Box(low=-inf, high=inf, shape=(35 + N*50,))
    action_space: MultiDiscrete([5] * N)  # N stocks, 5 actions each
    
    Episode: one pass through the historical data (start_date to end_date)
    Step: one trading day
    """
    
    def __init__(self, data_path: str, config: dict):
        # Load exported Parquet files
        # Define observation and action spaces
        pass
    
    def reset(self) -> np.ndarray:
        # Reset to start of episode (first date in data)
        # Return initial observation (state vector for day 1)
        pass
    
    def step(self, action: np.ndarray) -> tuple:
        # Apply action to simulated portfolio
        # Advance to next day
        # Compute reward
        # Return (next_observation, reward, done, truncated, info)
        pass
```

**Training script** (`training/train_rl_agent.py`):

```python
from stable_baselines3 import PPO
from trading_environment import TradingEnvironment

# Load data
env = TradingEnvironment("./data/exported/", config={...})

# Train
model = PPO("MlpPolicy", env, verbose=1, 
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99)
model.learn(total_timesteps=1_000_000)

# Export to ONNX
# (using SB3's documented ONNX export process)
export_to_onnx(model, "rl_trading_agent_v1.onnx")
```

**Deployment workflow:**
```
1. Export data from server:     GET /api/data-collection/export → download Parquet files
2. Transfer to training machine
3. Train RL agent:              python train_rl_agent.py
4. Export to ONNX:              → rl_trading_agent_v1.onnx
5. Upload to server:            POST /api/rl-models/upload (ONNX file + metadata)
6. Activate model:              POST /api/rl-models/{id}/activate
7. Switch to trading mode:      PUT /api/system/mode {"mode": "trading"}
```

**Files to create:**
- `training/rl_environment.py`
- `training/train_rl_agent.py`
- `training/requirements-rl.txt`
- `training/README.md`

---

## File Inventory

### New Files
| File | Phase | Purpose |
|------|-------|---------|
| `backend/alembic/versions/0015_add_rl_tables.py` | 1 | Migration for new tables |
| `backend/app/models/rl_snapshot.py` | 1 | RLStateSnapshot + RLStockSnapshot models |
| `backend/app/models/rl_model.py` | 1 | RLModel registry model |
| `backend/app/engine/state_snapshots.py` | 1 | Snapshot capture service |
| `backend/app/tasks/snapshot_tasks.py` | 1 | Celery task for daily snapshots |
| `backend/app/api/data_collection.py` | 1 | Data collection status + export API |
| `frontend/src/app/data-collection/page.tsx` | 1 | Data collection dashboard |
| `backend/app/engine/rl_agent.py` | 2 | ONNX-based RL agent stub |
| `backend/app/tasks/rl_tasks.py` | 2 | RL inference task (stub) |
| `backend/app/api/rl_models.py` | 2 | RL model upload/management API |
| `scripts/backfill_snapshots.py` | 3 | Reconstruct historical snapshots |
| `scripts/export_rl_data.py` | 3 | Export to Parquet for training |
| `training/rl_environment.py` | 4 | Gymnasium environment for training |
| `training/train_rl_agent.py` | 4 | Training script |
| `training/requirements-rl.txt` | 4 | Training dependencies |
| `training/README.md` | 4 | Training instructions |

### Modified Files
| File | Phase | Change |
|------|-------|--------|
| `backend/app/models/__init__.py` | 1 | Register new models |
| `backend/app/models/risk.py` | 1 | Add system_mode column |
| `backend/app/main.py` | 1,2 | Register new routers |
| `backend/app/celery_app.py` | 1,2 | Add snapshot task, remove decision cycle |
| `backend/app/tasks/task_status.py` | 1 | Mode-aware task gating |
| `backend/app/api/system.py` | 1 | Mode switching endpoints |
| `frontend/src/components/sidebar.tsx` | 1 | Add Data Collection, mode indicator |
| `frontend/src/lib/api.ts` | 1,2 | New API functions |
| `backend/app/engine/decision_engine.py` | 2 | Gut Claude decision, redirect to RL |
| `backend/app/config.py` | 2 | Remove signal weights, add RL config |
| `backend/app/tasks/decision_tasks.py` | 2 | Remove or redirect |
| `frontend/src/app/config/page.tsx` | 2 | Remove weights, add mode/model |
| `frontend/src/app/trades/page.tsx` | 2 | Mode-aware display |
| `frontend/src/app/models/page.tsx` | 2 | Add RL model section |

### Archived Files
| File | Phase | Reason |
|------|-------|--------|
| `backend/app/analysis/prompts/decision.txt` | 2 | Moved to prompts/archive/ |

## Server Dependencies

Add to `pyproject.toml`:
```toml
# RL inference (ONNX Runtime — lightweight, no PyTorch needed on server)
onnxruntime = ">=1.17"
# Export (already have pandas, add pyarrow for Parquet)
pyarrow = ">=15.0"
```

The server does NOT need PyTorch, TensorFlow, stable-baselines3, or gymnasium. Only `onnxruntime` (~50MB) for inference.

## Verification Criteria

After Phase 1:
- System runs in `data_collection` mode
- Daily snapshots appear in `rl_state_snapshots` table at 4:05 PM ET
- Data Collection page shows snapshot count, coverage, quality metrics
- Pause/resume correctly stops/starts snapshot capture
- No decision cycle runs, no trade proposals created

After Phase 2:
- Claude decision code removed from decision engine
- Signal weight config removed from UI
- RL agent stub loaded, returns NotImplementedError when called
- Model upload endpoint accepts ONNX files
- Trading mode is disabled (grayed out) until model uploaded

After Phase 3:
- Historical snapshots backfilled from first day of data
- Parquet export produces valid, complete dataset
- Feature normalization is correct (no data leakage across dates)

After Phase 4:
- Training environment can replay exported data
- Training produces convergent reward curves
- ONNX export produces valid model that loads on server
- Full round-trip: export data → train → upload model → activate → RL inference runs