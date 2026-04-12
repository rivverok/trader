# RL Trading Agent — Training Guide

Train a reinforcement learning agent on historical market data exported from the trading platform, then deploy the trained model back to the server for live inference.

## Prerequisites

- Python 3.11+
- GPU recommended (but not required for small datasets)
- Exported training data from the server (Parquet files)

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements-rl.txt

# For GPU support, install PyTorch with CUDA:
# pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## End-to-End Workflow

### 1. Export data from server

```bash
# Option A: API export
curl -o snapshots.parquet "https://your-server/api/data-collection/export?format=parquet"

# Option B: Run export script on server
cd backend && python -m scripts.export_rl_data --output ./data/exported
```

Transfer the exported directory to the training machine. It should contain:
- `states.parquet` — per-stock features indexed by (date, symbol)
- `portfolio.parquet` — portfolio features indexed by date
- `market.parquet` — market features indexed by date
- `metadata.json` — feature names, normalization params, date range

### 2. Train the agent

```bash
# Default: PPO with 1M timesteps
python train_rl_agent.py --data ./data/exported --output ./models

# Custom training
python train_rl_agent.py \
    --data ./data/exported \
    --output ./models \
    --algo PPO \
    --timesteps 2000000 \
    --reward risk_adjusted \
    --seed 42
```

**Algorithms available:**
| Algorithm | Best for | Notes |
|-----------|----------|-------|
| PPO | General purpose, stable | Default choice |
| A2C | Faster training, less stable | Good for quick experiments |

**Reward functions:**
| Type | Description |
|------|-------------|
| `simple_return` | Raw daily portfolio return |
| `risk_adjusted` | Return minus volatility penalty (default) |
| `log_return` | Log(1 + return) — reduces outlier impact |
| `asymmetric` | Losses penalized 2x more than gains |

### 3. Monitor training

```bash
# TensorBoard (training logs are saved automatically)
tensorboard --logdir ./models/tb_logs
```

### 4. Upload model to server

```bash
# Upload the ONNX model file
curl -X POST "https://your-server/api/rl-models/upload" \
    -F "file=@./models/rl_trading_ppo_v20250410_120000.onnx" \
    -F "name=rl_trading_ppo_v1" \
    -F "version=1.0.0" \
    -F "algorithm=PPO"

# Activate the model
curl -X POST "https://your-server/api/rl-models/{id}/activate"

# Switch to trading mode
curl -X PUT "https://your-server/api/system/mode" \
    -H "Content-Type: application/json" \
    -d '{"mode": "trading"}'
```

## Files

| File | Purpose |
|------|---------|
| `rl_environment.py` | Gymnasium environment — replays exported snapshots |
| `train_rl_agent.py` | Training script — PPO/A2C + ONNX export |
| `requirements-rl.txt` | Python dependencies for training |
| `train_technical_model.py` | Legacy ML model training (XGBoost/LightGBM) |
| `backtest_strategies.py` | Legacy backtesting strategies |

## Architecture Notes

- **Training** happens on a GPU machine with PyTorch + stable-baselines3
- **Inference** runs on the server with only `onnxruntime` (no PyTorch needed)
- ONNX is the deployment format — framework-agnostic, fast C++ runtime
- The environment replays historical snapshots offline (no live data during training)
- State vector: portfolio features + market features + per-stock features (concatenated)
- Action space: MultiDiscrete — one discrete action per stock (hold/buy_small/buy_large/sell_small/sell_all)

## Iterating

1. Collect more data: leave the server in `data_collection` mode
2. Re-export: `python -m scripts.export_rl_data --output ./data/exported`
3. Retrain: `python train_rl_agent.py --data ./data/exported`
4. Upload new model version, activate, compare performance
