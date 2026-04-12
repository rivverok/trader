"""Export RL state snapshots to Parquet files for training.

Reads snapshots from the database, normalizes features, and outputs:
  - states.parquet    — per-stock features indexed by (date, symbol)
  - portfolio.parquet — portfolio features indexed by date
  - market.parquet    — market features indexed by date
  - metadata.json     — feature names, normalization params, date range, stock universe
  - quality_report.txt — data quality summary (missing values, coverage gaps)

Usage:
    cd backend && python -m scripts.export_rl_data [--start 2024-01-01] [--end 2025-04-10] [--output ./data/exported]
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.rl_snapshot import RLStateSnapshot, RLStockSnapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
#  Feature column definitions
# ─────────────────────────────────────────────────────────────────────

# These are the flattened feature columns we extract from each JSONB blob.
# Missing values are filled with NaN and handled during normalization.

PRICE_FEATURES = [
    "close", "volume", "return_1d", "return_5d", "return_10d", "return_20d",
]

# Technical indicators we expect — compute_features outputs 100+ columns;
# we take whatever is present in the JSONB and flatten them.
# These are the "core" subset we specifically normalize.
CORE_TECHNICALS = [
    "rsi_14", "MACD_12_26_9", "MACDh_12_26_9", "atr_14",
    "sma_20", "sma_50", "sma_200", "ema_10", "ema_20",
    "bb_upper_20", "bb_lower_20", "adx_14",
    "stoch_k_14", "stoch_d_14", "obv", "cmf_20",
    "return_1d", "return_5d", "return_10d", "return_20d",
]

ML_SIGNAL_FEATURES = ["ml_confidence"]  # signal is categorical → one-hot encoded

SENTIMENT_FEATURES = [
    "avg_score", "min_score", "max_score", "num_articles", "material_events",
]

SYNTHESIS_FEATURES = ["overall_sentiment", "confidence"]

ANALYST_FEATURES = ["conviction", "time_horizon_days"]

RELATIVE_FEATURES = ["vs_spy_20d"]

PORTFOLIO_FEATURES = [
    "total_value", "cash", "positions_value", "cash_pct",
    "num_positions", "total_exposure_pct", "largest_position_pct",
    "daily_pnl", "daily_pnl_pct", "cumulative_pnl", "unrealized_pnl_total",
]

MARKET_FEATURES = [
    "spy_close", "spy_vs_sma50", "spy_vs_sma200", "spy_return_5d", "spy_return_20d",
    "fedfunds", "gs10", "gs2", "cpiaucsl", "unrate", "vixcls",
    "yield_curve_slope", "vix_normalized",
    "day_of_week", "month", "month_sin", "month_cos",
]


# ─────────────────────────────────────────────────────────────────────
#  Main export
# ─────────────────────────────────────────────────────────────────────


async def export_data(
    output_dir: str = "./data/exported",
    start_date: date | None = None,
    end_date: date | None = None,
):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    async with async_session() as db:
        # ── Load snapshots ───────────────────────────────────────────
        query = select(RLStateSnapshot).order_by(RLStateSnapshot.timestamp.asc())
        if start_date:
            query = query.where(
                func.date(RLStateSnapshot.timestamp) >= start_date
            )
        if end_date:
            query = query.where(
                func.date(RLStateSnapshot.timestamp) <= end_date
            )
        result = await db.execute(query)
        snapshots: list[RLStateSnapshot] = list(result.scalars().all())

        if not snapshots:
            logger.error("No snapshots found in date range")
            return

        logger.info("Loaded %d snapshots", len(snapshots))

        # ── Collect all stock snapshots ──────────────────────────────
        snapshot_ids = [s.id for s in snapshots]
        result = await db.execute(
            select(RLStockSnapshot)
            .where(RLStockSnapshot.snapshot_id.in_(snapshot_ids))
            .order_by(RLStockSnapshot.snapshot_id, RLStockSnapshot.symbol)
        )
        all_stock_snaps: list[RLStockSnapshot] = list(result.scalars().all())

        # Index stock snapshots by snapshot_id
        stock_by_snap: dict[int, list[RLStockSnapshot]] = defaultdict(list)
        for ss in all_stock_snaps:
            stock_by_snap[ss.snapshot_id].append(ss)

        logger.info(
            "Loaded %d stock snapshots across %d dates",
            len(all_stock_snaps), len(snapshots),
        )

    # ── Build DataFrames ─────────────────────────────────────────────
    state_rows = []
    portfolio_rows = []
    market_rows = []
    all_symbols: set[str] = set()
    all_tech_cols: set[str] = set()

    for snap in snapshots:
        snap_date = snap.timestamp.date().isoformat()
        stocks = stock_by_snap.get(snap.id, [])

        # Portfolio row
        pf = snap.portfolio_state or {}
        pf_row = {"date": snap_date}
        for feat in PORTFOLIO_FEATURES:
            pf_row[feat] = pf.get(feat)
        portfolio_rows.append(pf_row)

        # Market row
        mkt = snap.market_state or {}
        mkt_row = {"date": snap_date}
        for feat in MARKET_FEATURES:
            mkt_row[feat] = mkt.get(feat)
        market_rows.append(mkt_row)

        # Per-stock rows
        for ss in stocks:
            all_symbols.add(ss.symbol)
            row: dict = {"date": snap_date, "symbol": ss.symbol}

            # Price features
            pd_data = ss.price_data or {}
            for feat in PRICE_FEATURES:
                row[f"price_{feat}"] = pd_data.get(feat)

            # Technical indicators — flatten all available
            tech = ss.technical_indicators or {}
            for k, v in tech.items():
                col_name = f"tech_{k}"
                row[col_name] = v
                all_tech_cols.add(col_name)

            # ML signal
            ml = ss.ml_signal or {}
            row["ml_confidence"] = ml.get("confidence")
            ml_sig = ml.get("signal")
            row["ml_signal_buy"] = 1.0 if ml_sig == "buy" else 0.0
            row["ml_signal_sell"] = 1.0 if ml_sig == "sell" else 0.0
            row["ml_signal_hold"] = 1.0 if ml_sig == "hold" else 0.0

            # Sentiment
            sent = ss.sentiment or {}
            for feat in SENTIMENT_FEATURES:
                row[f"sent_{feat}"] = sent.get(feat)

            # Synthesis
            syn = ss.synthesis or {}
            for feat in SYNTHESIS_FEATURES:
                row[f"synth_{feat}"] = syn.get(feat)

            # Analyst input
            ai = ss.analyst_input or {}
            row["analyst_conviction"] = ai.get("conviction")
            row["analyst_time_horizon"] = ai.get("time_horizon_days")
            override = ai.get("override_flag", "none")
            row["analyst_override_avoid"] = 1.0 if override == "avoid" else 0.0
            row["analyst_override_boost"] = 1.0 if override == "boost" else 0.0

            # Relative strength
            rel = ss.relative_strength or {}
            for feat in RELATIVE_FEATURES:
                row[f"rel_{feat}"] = rel.get(feat)

            state_rows.append(row)

    # ── Create DataFrames ────────────────────────────────────────────
    states_df = pd.DataFrame(state_rows)
    portfolio_df = pd.DataFrame(portfolio_rows)
    market_df = pd.DataFrame(market_rows)

    logger.info(
        "DataFrames: states=%s, portfolio=%s, market=%s",
        states_df.shape, portfolio_df.shape, market_df.shape,
    )

    # ── Normalize numeric columns ────────────────────────────────────
    normalization_params = {}

    states_df, norm_states = _normalize_df(
        states_df, exclude_cols={"date", "symbol"}
    )
    normalization_params["states"] = norm_states

    portfolio_df, norm_pf = _normalize_df(portfolio_df, exclude_cols={"date"})
    normalization_params["portfolio"] = norm_pf

    market_df, norm_mkt = _normalize_df(market_df, exclude_cols={"date"})
    normalization_params["market"] = norm_mkt

    # ── Write Parquet files ──────────────────────────────────────────
    states_df.to_parquet(output_path / "states.parquet", index=False)
    portfolio_df.to_parquet(output_path / "portfolio.parquet", index=False)
    market_df.to_parquet(output_path / "market.parquet", index=False)

    logger.info("Written Parquet files to %s", output_path)

    # ── Write metadata ───────────────────────────────────────────────
    first_date = snapshots[0].timestamp.date().isoformat()
    last_date = snapshots[-1].timestamp.date().isoformat()

    metadata = {
        "date_range": {"start": first_date, "end": last_date},
        "num_snapshots": len(snapshots),
        "num_stock_records": len(state_rows),
        "stock_universe": sorted(all_symbols),
        "num_stocks": len(all_symbols),
        "feature_columns": {
            "states": [c for c in states_df.columns if c not in {"date", "symbol"}],
            "portfolio": [c for c in portfolio_df.columns if c != "date"],
            "market": [c for c in market_df.columns if c != "date"],
        },
        "normalization": normalization_params,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(output_path / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    # ── Data quality report ──────────────────────────────────────────
    report_lines = _build_quality_report(
        states_df, portfolio_df, market_df, snapshots, all_symbols
    )
    report_text = "\n".join(report_lines)
    (output_path / "quality_report.txt").write_text(report_text)

    logger.info("Export complete — %d snapshots, %d stocks", len(snapshots), len(all_symbols))
    print(report_text)


# ─────────────────────────────────────────────────────────────────────
#  Normalization
# ─────────────────────────────────────────────────────────────────────


def _normalize_df(
    df: pd.DataFrame, exclude_cols: set[str]
) -> tuple[pd.DataFrame, dict]:
    """Standard-scale numeric columns. Returns (normalized_df, params_dict)."""
    params = {}
    df = df.copy()

    for col in df.columns:
        if col in exclude_cols:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        series = df[col].astype(float)
        mean = series.mean()
        std = series.std()

        if pd.isna(mean):
            mean = 0.0
        if pd.isna(std) or std == 0:
            std = 1.0

        df[col] = (series - mean) / std
        params[col] = {"mean": float(mean), "std": float(std)}

    return df, params


# ─────────────────────────────────────────────────────────────────────
#  Quality report
# ─────────────────────────────────────────────────────────────────────


def _build_quality_report(
    states_df: pd.DataFrame,
    portfolio_df: pd.DataFrame,
    market_df: pd.DataFrame,
    snapshots: list,
    symbols: set[str],
) -> list[str]:
    """Build a text quality report about the exported data."""
    lines = [
        "=" * 60,
        "  RL Training Data — Quality Report",
        "=" * 60,
        "",
        f"Date range:   {snapshots[0].timestamp.date()} → {snapshots[-1].timestamp.date()}",
        f"Snapshots:    {len(snapshots)}",
        f"Stocks:       {len(symbols)}",
        f"Stock records: {len(states_df)}",
        "",
        "─" * 60,
        "  Missing Values (states.parquet)",
        "─" * 60,
    ]

    if not states_df.empty:
        total_cells = len(states_df)
        for col in sorted(states_df.columns):
            if col in ("date", "symbol"):
                continue
            null_count = states_df[col].isna().sum()
            if null_count > 0:
                pct = null_count / total_cells * 100
                lines.append(f"  {col:40s}  {null_count:6d} ({pct:5.1f}%)")

    lines.extend([
        "",
        "─" * 60,
        "  Missing Values (portfolio.parquet)",
        "─" * 60,
    ])

    if not portfolio_df.empty:
        total_cells = len(portfolio_df)
        for col in sorted(portfolio_df.columns):
            if col == "date":
                continue
            null_count = portfolio_df[col].isna().sum()
            if null_count > 0:
                pct = null_count / total_cells * 100
                lines.append(f"  {col:40s}  {null_count:6d} ({pct:5.1f}%)")

    lines.extend([
        "",
        "─" * 60,
        "  Missing Values (market.parquet)",
        "─" * 60,
    ])

    if not market_df.empty:
        total_cells = len(market_df)
        for col in sorted(market_df.columns):
            if col == "date":
                continue
            null_count = market_df[col].isna().sum()
            if null_count > 0:
                pct = null_count / total_cells * 100
                lines.append(f"  {col:40s}  {null_count:6d} ({pct:5.1f}%)")

    # ── Coverage per symbol ──────────────────────────────────────────
    lines.extend([
        "",
        "─" * 60,
        "  Stock Coverage (dates per symbol)",
        "─" * 60,
    ])

    if not states_df.empty:
        coverage = states_df.groupby("symbol")["date"].nunique().sort_values(ascending=False)
        max_dates = len(states_df["date"].unique())
        for sym, count in coverage.items():
            pct = count / max_dates * 100
            lines.append(f"  {sym:10s}  {count:5d} / {max_dates} ({pct:5.1f}%)")

    lines.extend(["", "=" * 60])
    return lines


# ─────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Export RL snapshots to Parquet")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default="./data/exported", help="Output directory")
    args = parser.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    asyncio.run(export_data(output_dir=args.output, start_date=start, end_date=end))


if __name__ == "__main__":
    main()
