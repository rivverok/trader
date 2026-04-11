"""Backtesting engine — simulates trading strategies on historical data.

Uses vectorbt for fast vectorized backtesting with realistic assumptions.

Usage:
    python -m training.backtest_strategies --model models/xgboost_v1.joblib \\
        --start 2021-01-01 --end 2025-12-31
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_SLIPPAGE = 0.001     # 0.1%
DEFAULT_COMMISSION = 1.0     # $1 per trade
DEFAULT_INITIAL_CASH = 100_000.0


def run_backtest(
    model_path: str,
    price_data: pd.DataFrame,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    slippage: float = DEFAULT_SLIPPAGE,
    commission: float = DEFAULT_COMMISSION,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Run a backtest using a trained model on price data.

    Args:
        model_path: Path to the .joblib model artifact.
        price_data: DataFrame with columns [symbol, timestamp, open, high, low, close, volume].
        initial_cash: Starting portfolio value.
        slippage: Per-trade slippage fraction.
        commission: Per-trade commission in dollars.
        start_date: ISO date to start the backtest.
        end_date: ISO date to end the backtest.

    Returns:
        Dict with backtest metrics and detailed results.
    """
    import vectorbt as vbt

    from app.ml.feature_engineering import LABEL_MAP, compute_features, get_feature_columns

    artifact = joblib.load(model_path)
    model = artifact["model"]
    feature_names = artifact["feature_names"]
    model_name = artifact.get("model_type", "unknown")
    version = artifact.get("version", "unknown")

    symbols = price_data["symbol"].unique().tolist()
    all_results = {}

    for symbol in symbols:
        sym_df = price_data[price_data["symbol"] == symbol].copy()
        sym_df = sym_df.set_index("timestamp").sort_index()
        sym_df = sym_df[["open", "high", "low", "close", "volume"]]

        # Filter date range
        if start_date:
            sym_df = sym_df[sym_df.index >= pd.Timestamp(start_date)]
        if end_date:
            sym_df = sym_df[sym_df.index <= pd.Timestamp(end_date)]

        if len(sym_df) < 200:
            logger.warning("Skipping %s — only %d rows in date range", symbol, len(sym_df))
            continue

        # Compute features
        featured = compute_features(sym_df)
        feat_cols = [c for c in feature_names if c in featured.columns]
        if len(feat_cols) < len(feature_names) * 0.8:
            logger.warning("Skipping %s — insufficient features", symbol)
            continue

        # Fill missing features
        for col in feature_names:
            if col not in featured.columns:
                featured[col] = 0.0

        clean = featured.dropna(subset=feat_cols)
        if len(clean) < 50:
            continue

        X = clean[feature_names].fillna(0)

        # Generate signals for each row
        preds = model.predict(X)
        signals_series = pd.Series(preds, index=clean.index)

        # Create entry/exit signals for vectorbt
        # Buy when signal=0 (buy), sell when signal=2 (sell)
        entries = signals_series == 0  # buy
        exits = signals_series == 2   # sell

        # Run portfolio simulation
        close_prices = clean["close"]

        pf = vbt.Portfolio.from_signals(
            close_prices,
            entries=entries,
            exits=exits,
            init_cash=initial_cash / len(symbols),  # Split cash across symbols
            fees=slippage + (commission / (initial_cash / len(symbols)) * 0.01),
            freq="1D",
        )

        stats = pf.stats()

        # Benchmark: buy and hold
        benchmark_return = float(
            (close_prices.iloc[-1] / close_prices.iloc[0]) - 1.0
        )

        symbol_result = {
            "symbol": symbol,
            "total_return": float(stats.get("Total Return [%]", 0)) / 100,
            "sharpe_ratio": float(stats.get("Sharpe Ratio", 0)),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0)) / 100,
            "win_rate": float(stats.get("Win Rate [%]", 0)) / 100,
            "total_trades": int(stats.get("Total Trades", 0)),
            "profit_factor": float(stats.get("Profit Factor", 0)),
            "benchmark_return": benchmark_return,
            "start_date": str(clean.index[0].date()),
            "end_date": str(clean.index[-1].date()),
            "data_points": len(clean),
        }
        all_results[symbol] = symbol_result
        logger.info("Backtest %s: return=%.2f%%, sharpe=%.2f, trades=%d",
                     symbol, symbol_result["total_return"] * 100,
                     symbol_result["sharpe_ratio"], symbol_result["total_trades"])

    if not all_results:
        raise RuntimeError("No symbols had sufficient data for backtesting")

    # Aggregate metrics across all symbols
    returns = [r["total_return"] for r in all_results.values()]
    sharpes = [r["sharpe_ratio"] for r in all_results.values()]
    drawdowns = [r["max_drawdown"] for r in all_results.values()]
    win_rates = [r["win_rate"] for r in all_results.values()]
    trade_counts = [r["total_trades"] for r in all_results.values()]
    profit_factors = [r["profit_factor"] for r in all_results.values() if r["profit_factor"] > 0]
    benchmark_returns = [r["benchmark_return"] for r in all_results.values()]

    summary = {
        "model_name": model_name,
        "model_version": version,
        "model_path": str(model_path),
        "strategy_name": f"ml_signals_{model_name}",
        "symbols": symbols,
        "initial_cash": initial_cash,
        "slippage": slippage,
        "commission": commission,
        "aggregate": {
            "avg_total_return": float(np.mean(returns)),
            "avg_sharpe_ratio": float(np.mean(sharpes)),
            "avg_max_drawdown": float(np.mean(drawdowns)),
            "avg_win_rate": float(np.mean(win_rates)),
            "total_trades": int(np.sum(trade_counts)),
            "avg_profit_factor": float(np.mean(profit_factors)) if profit_factors else 0.0,
            "avg_benchmark_return": float(np.mean(benchmark_returns)),
        },
        "per_symbol": all_results,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return summary


def load_prices_from_db(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Load price data from database for backtesting."""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL", "postgresql://trader:trader@localhost:5432/trader")
    db_url = db_url.replace("+asyncpg", "")
    engine = create_engine(db_url)

    placeholders = ", ".join(f":sym{i}" for i in range(len(symbols)))
    params = {f"sym{i}": s for i, s in enumerate(symbols)}
    params["start"] = start_date
    params["end"] = end_date

    query = text(f"""
        SELECT s.symbol, p.timestamp, p.open, p.high, p.low, p.close, p.volume
        FROM prices p
        JOIN stocks s ON s.id = p.stock_id
        WHERE s.symbol IN ({placeholders})
          AND p.interval = '1Day'
          AND p.timestamp >= :start
          AND p.timestamp <= :end
        ORDER BY s.symbol, p.timestamp
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params, parse_dates=["timestamp"])

    return df


def main():
    parser = argparse.ArgumentParser(description="Backtest ML trading strategies")
    parser.add_argument("--model", type=str, required=True, help="Path to .joblib model file")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (default: from model)")
    parser.add_argument("--csv", type=str, help="CSV file with price data")
    parser.add_argument("--start", type=str, default="2021-01-01", help="Start date")
    parser.add_argument("--end", type=str, default="2025-12-31", help="End date")
    parser.add_argument("--cash", type=float, default=DEFAULT_INITIAL_CASH, help="Initial cash")
    parser.add_argument("--slippage", type=float, default=DEFAULT_SLIPPAGE)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION)
    args = parser.parse_args()

    # Load price data
    if args.csv:
        price_data = pd.read_csv(args.csv, parse_dates=["timestamp"])
    else:
        artifact = joblib.load(args.model)
        symbols = args.symbols.split(",") if args.symbols else artifact.get("symbols", [])
        if not symbols:
            parser.error("No symbols specified and model has no symbol list")
        price_data = load_prices_from_db(symbols, args.start, args.end)

    results = run_backtest(
        model_path=args.model,
        price_data=price_data,
        initial_cash=args.cash,
        slippage=args.slippage,
        commission=args.commission,
        start_date=args.start,
        end_date=args.end,
    )

    # Save report
    report_path = Path(args.model).parent / f"backtest_{Path(args.model).stem}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n" + "=" * 60)
    agg = results["aggregate"]
    print(f"Strategy: {results['strategy_name']}")
    print(f"Symbols: {', '.join(results['symbols'])}")
    print(f"Avg Return: {agg['avg_total_return']:.2%}")
    print(f"Avg Sharpe: {agg['avg_sharpe_ratio']:.2f}")
    print(f"Avg Max DD: {agg['avg_max_drawdown']:.2%}")
    print(f"Avg Win Rate: {agg['avg_win_rate']:.2%}")
    print(f"Total Trades: {agg['total_trades']}")
    print(f"Benchmark: {agg['avg_benchmark_return']:.2%}")
    print(f"Report: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
