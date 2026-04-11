"""Walk-forward model training pipeline.

Designed to run on the GPU training PC or the trading server.
Connects to PostgreSQL, loads historical price data, engineers features,
trains XGBoost + LightGBM with walk-forward validation, and exports
the best model as a .joblib file.

Usage:
    python -m training.train_technical_model --symbols AAPL,MSFT --years 5
    python -m training.train_technical_model --csv data/prices.csv
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score, precision_score, recall_score

# Add parent directory so we can import from backend/app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "ml" / "models"


def load_from_database(symbols: list[str], years: int = 5) -> pd.DataFrame:
    """Load historical daily price data from PostgreSQL."""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://trader:trader@localhost:5432/trader",
    )
    # Ensure we use a sync driver
    db_url = db_url.replace("+asyncpg", "")
    engine = create_engine(db_url)

    cutoff = datetime.now(timezone.utc) - timedelta(days=years * 365)
    placeholders = ", ".join(f":sym{i}" for i in range(len(symbols)))
    params = {f"sym{i}": s for i, s in enumerate(symbols)}
    params["cutoff"] = cutoff

    query = text(f"""
        SELECT s.symbol, p.timestamp, p.open, p.high, p.low, p.close, p.volume
        FROM prices p
        JOIN stocks s ON s.id = p.stock_id
        WHERE s.symbol IN ({placeholders})
          AND p.interval = '1Day'
          AND p.timestamp >= :cutoff
        ORDER BY s.symbol, p.timestamp
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params, parse_dates=["timestamp"])

    logger.info("Loaded %d rows from database for %s", len(df), symbols)
    return df


def load_from_csv(csv_path: str) -> pd.DataFrame:
    """Load price data from a CSV file."""
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV must have columns: {required}")
    logger.info("Loaded %d rows from %s", len(df), csv_path)
    return df


def walk_forward_split(
    df: pd.DataFrame,
    train_years: int = 3,
    test_months: int = 6,
    step_months: int = 6,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Generate walk-forward train/test splits.

    Returns list of (train_df, test_df) tuples.
    """
    df = df.sort_index()
    start = df.index.min()
    end = df.index.max()

    train_delta = pd.DateOffset(years=train_years)
    test_delta = pd.DateOffset(months=test_months)
    step_delta = pd.DateOffset(months=step_months)

    splits = []
    cursor = start

    while cursor + train_delta + test_delta <= end:
        train_end = cursor + train_delta
        test_end = train_end + test_delta

        train_df = df[cursor:train_end]
        test_df = df[train_end:test_end]

        if len(train_df) > 100 and len(test_df) > 20:
            splits.append((train_df, test_df))

        cursor += step_delta

    logger.info("Generated %d walk-forward splits", len(splits))
    return splits


def train_and_evaluate(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Train both XGBoost and LightGBM, return metrics for both."""
    import lightgbm as lgb
    import xgboost as xgb

    results = {}

    # ── XGBoost ──────────────────────────────────────────────────────
    xgb_model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
        tree_method="hist",  # GPU: change to "gpu_hist" if CUDA available
        early_stopping_rounds=50,
    )
    xgb_model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    xgb_preds = xgb_model.predict(X_test)
    results["xgboost"] = {
        "model": xgb_model,
        "accuracy": float(accuracy_score(y_test, xgb_preds)),
        "f1_macro": float(f1_score(y_test, xgb_preds, average="macro")),
        "precision_macro": float(precision_score(y_test, xgb_preds, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, xgb_preds, average="macro", zero_division=0)),
        "report": classification_report(y_test, xgb_preds, output_dict=True, zero_division=0),
    }

    # ── LightGBM ─────────────────────────────────────────────────────
    lgb_model = lgb.LGBMClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="multiclass",
        num_class=3,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    lgb_model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    lgb_preds = lgb_model.predict(X_test)
    results["lightgbm"] = {
        "model": lgb_model,
        "accuracy": float(accuracy_score(y_test, lgb_preds)),
        "f1_macro": float(f1_score(y_test, lgb_preds, average="macro")),
        "precision_macro": float(precision_score(y_test, lgb_preds, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, lgb_preds, average="macro", zero_division=0)),
        "report": classification_report(y_test, lgb_preds, output_dict=True, zero_division=0),
    }

    return results


def get_feature_importances(model, feature_names: list[str], top_n: int = 20) -> dict[str, float]:
    """Extract top-N feature importances from a trained model."""
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:top_n]
    return {feature_names[i]: float(importances[i]) for i in indices}


def run_training(
    df_all: pd.DataFrame,
    forward_days: int = 5,
    buy_threshold: float = 0.02,
    sell_threshold: float = -0.02,
    train_years: int = 3,
    test_months: int = 6,
    progress_callback=None,
) -> dict:
    """Full training pipeline for all symbols in the dataframe.

    Returns training report dict with model path, metrics per fold, etc.
    """
    from app.ml.feature_engineering import compute_features, generate_labels, get_feature_columns

    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    symbols = df_all["symbol"].unique().tolist()
    all_fold_metrics = []
    best_model = None
    best_score = -1.0
    best_model_type = ""
    feature_names = []
    total_symbols = len(symbols)

    # Process each symbol
    for sym_idx, symbol in enumerate(symbols):
        sym_df = df_all[df_all["symbol"] == symbol].copy()
        sym_df = sym_df.set_index("timestamp").sort_index()
        sym_df = sym_df[["open", "high", "low", "close", "volume"]]

        # Feature engineering
        sym_df = compute_features(sym_df)
        sym_df = generate_labels(sym_df, forward_days, buy_threshold, sell_threshold)

        feat_cols = get_feature_columns(sym_df)
        clean = sym_df.dropna(subset=["label"] + feat_cols)

        if len(clean) < 500:
            logger.warning("Skipping %s — only %d clean rows", symbol, len(clean))
            continue

        feature_names = feat_cols

        # Walk-forward validation
        splits = walk_forward_split(clean, train_years, test_months)
        if not splits:
            logger.warning("No valid splits for %s", symbol)
            continue

        total_folds = len(splits)
        for fold_idx, (train_df, test_df) in enumerate(splits):
            X_train = train_df[feat_cols]
            y_train = train_df["label"].astype(int)
            X_test = test_df[feat_cols]
            y_test = test_df["label"].astype(int)

            logger.info(
                "Fold %d for %s: train=%d, test=%d",
                fold_idx, symbol, len(X_train), len(X_test),
            )

            if progress_callback:
                progress_callback(
                    symbol=symbol,
                    sym_idx=sym_idx,
                    total_symbols=total_symbols,
                    fold_idx=fold_idx,
                    total_folds=total_folds,
                    best_score=best_score,
                    best_model_type=best_model_type,
                )

            results = train_and_evaluate(X_train, y_train, X_test, y_test)

            for model_type, metrics in results.items():
                fold_record = {
                    "symbol": symbol,
                    "fold": fold_idx,
                    "model_type": model_type,
                    "accuracy": metrics["accuracy"],
                    "f1_macro": metrics["f1_macro"],
                    "precision_macro": metrics["precision_macro"],
                    "recall_macro": metrics["recall_macro"],
                    "train_rows": len(X_train),
                    "test_rows": len(X_test),
                }
                all_fold_metrics.append(fold_record)

                # Track best model by F1 macro
                if metrics["f1_macro"] > best_score:
                    best_score = metrics["f1_macro"]
                    best_model = metrics["model"]
                    best_model_type = model_type

    if best_model is None:
        raise RuntimeError("No model was trained — insufficient data")

    # ── Save best model ──────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = f"v_{timestamp}"
    filename = f"{best_model_type}_{version}.joblib"
    model_path = MODEL_OUTPUT_DIR / filename

    joblib.dump(
        {
            "model": best_model,
            "feature_names": feature_names,
            "model_type": best_model_type,
            "version": version,
            "training_date": datetime.now(timezone.utc).isoformat(),
            "forward_days": forward_days,
            "buy_threshold": buy_threshold,
            "sell_threshold": sell_threshold,
            "symbols": symbols,
        },
        model_path,
    )
    logger.info("Saved best model (%s, F1=%.4f) to %s", best_model_type, best_score, model_path)

    # ── Feature importances ──────────────────────────────────────────
    top_features = get_feature_importances(best_model, feature_names)

    # ── Build training report ────────────────────────────────────────
    report = {
        "model_name": best_model_type,
        "version": version,
        "file_path": str(model_path),
        "training_date": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "feature_count": len(feature_names),
        "fold_metrics": all_fold_metrics,
        "best_f1_macro": best_score,
        "top_feature_importances": top_features,
        "parameters": {
            "forward_days": forward_days,
            "buy_threshold": buy_threshold,
            "sell_threshold": sell_threshold,
        },
    }

    # Save report JSON alongside model
    report_path = MODEL_OUTPUT_DIR / f"report_{version}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("Training report saved to %s", report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description="Train technical signal models")
    parser.add_argument("--symbols", type=str, help="Comma-separated stock symbols")
    parser.add_argument("--csv", type=str, help="Path to CSV with price data")
    parser.add_argument("--years", type=int, default=5, help="Years of history to use")
    parser.add_argument("--forward-days", type=int, default=5, help="Forward return period")
    parser.add_argument("--buy-threshold", type=float, default=0.02, help="Buy label threshold")
    parser.add_argument("--sell-threshold", type=float, default=-0.02, help="Sell label threshold")
    args = parser.parse_args()

    if args.csv:
        df = load_from_csv(args.csv)
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
        df = load_from_database(symbols, args.years)
    else:
        parser.error("Either --symbols or --csv is required")

    report = run_training(
        df,
        forward_days=args.forward_days,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
    )

    print("\n" + "=" * 60)
    print(f"Model: {report['model_name']} {report['version']}")
    print(f"Best F1 Macro: {report['best_f1_macro']:.4f}")
    print(f"Features: {report['feature_count']}")
    print(f"Saved to: {report['file_path']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
