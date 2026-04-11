#!/usr/bin/env python3
"""Remote ML training client.

Connects to the AI Trading Platform API, downloads training data,
trains XGBoost/LightGBM models locally, and uploads the result back.

Setup (one-time):
    python -m venv .venv
    .venv\\Scripts\\activate        # Windows
    pip install -r scripts/requirements-training.txt

Usage:
    python scripts/remote_train.py --server http://riv-ubuntu:5000
    python scripts/remote_train.py --server http://riv-ubuntu:5000 --years 3
    python scripts/remote_train.py --server http://riv-ubuntu:5000 --check-only
"""

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

# Add the project root and backend to sys.path so we can import training code
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT))


def check_staleness(server: str) -> dict:
    """Check if the active model is stale."""
    resp = requests.get(f"{server}/api/models/staleness", timeout=10)
    resp.raise_for_status()
    return resp.json()


def download_training_data(server: str, years: int) -> pd.DataFrame:
    """Download OHLCV training data from the server as CSV."""
    print(f"\nDownloading training data ({years} years)...")
    resp = requests.get(
        f"{server}/api/models/training-data",
        params={"years": years},
        timeout=60,
        stream=True,
    )
    resp.raise_for_status()

    # Read streaming CSV into DataFrame
    csv_data = resp.text
    df = pd.read_csv(io.StringIO(csv_data), parse_dates=["timestamp"])

    symbols = df["symbol"].nunique()
    print(f"  Downloaded {len(df):,} rows for {symbols} stocks")
    return df


def upload_model(server: str, model_path: Path, report_path: Path) -> dict:
    """Upload trained model and report to the server."""
    print(f"\nUploading model to {server}...")
    with open(model_path, "rb") as mf, open(report_path, "rb") as rf:
        resp = requests.post(
            f"{server}/api/models/upload",
            files={
                "model_file": (model_path.name, mf, "application/octet-stream"),
                "report_file": (report_path.name, rf, "application/json"),
            },
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Remote ML training client for AI Trading Platform",
    )
    parser.add_argument(
        "--server",
        required=True,
        help="Server URL (e.g. http://riv-ubuntu:5000)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Years of historical data to use (default: 5)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check model staleness, don't train",
    )
    args = parser.parse_args()

    server = args.server.rstrip("/")

    # ── Step 1: Check staleness ──────────────────────────────────────
    print("=" * 60)
    print("AI Trading Platform — Remote Training")
    print("=" * 60)
    print(f"\nServer: {server}")

    try:
        staleness = check_staleness(server)
    except requests.ConnectionError:
        print(f"\nERROR: Cannot connect to {server}")
        print("Make sure the server is running and accessible on your network.")
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"\nERROR: Server returned {e.response.status_code}")
        sys.exit(1)

    if staleness.get("active_model_age_days") is not None:
        print(f"\nActive model age: {staleness['active_model_age_days']} days")
        print(f"Active model F1:  {staleness.get('active_model_f1', 'N/A')}")
        print(f"Stale threshold:  {staleness['threshold_days']} days")
        print(f"Status:           {'STALE — retraining recommended' if staleness['stale'] else 'OK'}")
    else:
        print("\nNo active model found — training required")

    if args.check_only:
        sys.exit(0)

    # ── Step 2: Download training data ───────────────────────────────
    try:
        df = download_training_data(server, args.years)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print("\nERROR: No price data found on server. Collect data first.")
        else:
            print(f"\nERROR: Failed to download data: {e}")
        sys.exit(1)

    if len(df) < 500:
        print(f"\nERROR: Only {len(df)} rows downloaded — need at least 500 for training")
        sys.exit(1)

    # ── Step 3: Train locally ────────────────────────────────────────
    print("\nStarting local training...")
    print("-" * 60)

    from training.train_technical_model import run_training

    # Override MODEL_OUTPUT_DIR to use a temp directory
    import training.train_technical_model as train_module
    tmpdir = Path(tempfile.mkdtemp(prefix="trader_model_"))
    train_module.MODEL_OUTPUT_DIR = tmpdir

    try:
        report = run_training(df)
    except RuntimeError as e:
        print(f"\nERROR: Training failed: {e}")
        sys.exit(1)

    print("-" * 60)
    print(f"\nTraining complete!")
    print(f"  Model:    {report['model_name']}")
    print(f"  Version:  {report['version']}")
    print(f"  F1 Macro: {report['best_f1_macro']:.4f}")
    print(f"  Features: {report['feature_count']}")

    # ── Step 4: Upload to server ─────────────────────────────────────
    model_path = Path(report["file_path"])
    report_path = tmpdir / f"report_{report['version']}.json"

    result = upload_model(server, model_path, report_path)

    print("\n" + "=" * 60)
    if result["promoted"]:
        print("MODEL PROMOTED to active!")
        print(f"  New F1: {result['new_f1']:.4f}")
        if result.get("old_f1") is not None:
            print(f"  Old F1: {result['old_f1']:.4f}")
    else:
        print("Model uploaded but NOT promoted (F1 did not beat current active)")
        print(f"  New F1: {result['new_f1']:.4f}")
        print(f"  Old F1: {result.get('old_f1', 'N/A')}")
    print("=" * 60)

    # Cleanup temp files
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
