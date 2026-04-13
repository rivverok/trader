"""Technical signal inference — load trained model and produce signals.

Runs on the trading server. Loads the active model from disk,
computes features from latest price data, and generates buy/sell/hold
signals with confidence scores.
"""

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.feature_engineering import LABEL_MAP, compute_features
from app.models.ml import ModelRegistry
from app.models.price import Price
from app.models.signal import MLSignal
from app.models.stock import Stock

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"

# Cache the loaded model in-process
_cached_model: dict[str, Any] | None = None
_cached_model_version: str | None = None


def _load_model(file_path: str) -> dict[str, Any]:
    """Load model artifact from disk, with in-memory caching."""
    global _cached_model, _cached_model_version

    if _cached_model is not None and _cached_model_version == file_path:
        return _cached_model

    logger.info("Loading model from %s", file_path)
    artifact = joblib.load(file_path)
    _cached_model = artifact
    _cached_model_version = file_path
    return artifact


async def get_active_model(db_session: AsyncSession) -> ModelRegistry | None:
    """Get the currently active model from the registry."""
    result = await db_session.execute(
        select(ModelRegistry)
        .where(ModelRegistry.is_active.is_(True))
        .order_by(desc(ModelRegistry.training_date))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def generate_signal(
    db_session: AsyncSession,
    stock: Stock,
    model_registry: ModelRegistry | None = None,
) -> dict[str, Any] | None:
    """Generate a signal for a single stock using the active model.

    Returns dict with signal, confidence, feature_importances, or None if
    no model or insufficient data.
    """
    if model_registry is None:
        model_registry = await get_active_model(db_session)
    if model_registry is None:
        logger.warning("No active model found in registry")
        return None

    artifact = _load_model(model_registry.file_path)
    model = artifact["model"]
    feature_names = artifact["feature_names"]

    # Load recent price data (need 250 days for SMA_200 + buffer)
    result = await db_session.execute(
        select(Price)
        .where(Price.stock_id == stock.id, Price.interval == "1Day")
        .order_by(desc(Price.timestamp))
        .limit(300)
    )
    prices = result.scalars().all()

    if len(prices) < 200:
        logger.warning(
            "Insufficient price data for %s (%d rows, need 200+)",
            stock.symbol, len(prices),
        )
        return None

    # Build DataFrame
    df = pd.DataFrame([
        {
            "timestamp": p.timestamp,
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        }
        for p in prices
    ]).set_index("timestamp").sort_index()

    # Compute features
    df = compute_features(df)

    # Get the latest row that has all features
    available = [c for c in feature_names if c in df.columns]
    if len(available) < len(feature_names) * 0.8:
        logger.warning(
            "Too many missing features for %s (%d/%d available)",
            stock.symbol, len(available), len(feature_names),
        )
        return None

    latest = df.iloc[-1:]

    # Fill any missing feature columns with 0
    for col in feature_names:
        if col not in latest.columns:
            latest[col] = 0.0

    X = latest[feature_names].fillna(0)

    # Predict
    proba = model.predict_proba(X)[0]
    pred_class = int(np.argmax(proba))
    confidence = float(proba[pred_class])
    signal = LABEL_MAP.get(pred_class, "hold")

    # Feature importances (top-10 for this prediction)
    importances = dict(zip(
        feature_names,
        (model.feature_importances_ / model.feature_importances_.sum()).tolist(),
    ))
    top_importances = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10])

    return {
        "signal": signal,
        "confidence": confidence,
        "probabilities": {LABEL_MAP[i]: float(p) for i, p in enumerate(proba)},
        "feature_importances": top_importances,
        "model_name": model_registry.model_name,
        "model_version": model_registry.version,
    }


async def generate_all_signals(db_session: AsyncSession) -> dict[str, Any]:
    """Generate signals for all watchlist stocks.

    Stores MLSignal records in the database and returns a summary.
    """
    model_registry = await get_active_model(db_session)
    if model_registry is None:
        return {"status": "skip", "reason": "no active model"}

    result = await db_session.execute(
        select(Stock).where(Stock.on_watchlist.is_(True))
    )
    stocks = list(result.scalars().all())

    if not stocks:
        return {"status": "skip", "reason": "no watchlist stocks"}

    generated = 0
    errors = 0
    skipped = 0
    error_details: list[str] = []

    for stock in stocks:
        try:
            signal_data = await generate_signal(db_session, stock, model_registry)
            if signal_data is None:
                skipped += 1
                continue

            ml_signal = MLSignal(
                stock_id=stock.id,
                model_name=signal_data["model_name"],
                model_version=signal_data["model_version"],
                signal=signal_data["signal"],
                confidence=signal_data["confidence"],
                feature_importances=signal_data["feature_importances"],
            )
            db_session.add(ml_signal)
            generated += 1
        except Exception as e:
            logger.error("Signal generation failed for %s: %s", stock.symbol, e, exc_info=True)
            errors += 1
            if len(error_details) < 3:
                error_details.append(f"{stock.symbol}: {type(e).__name__}: {e}")

    await db_session.commit()

    result = {
        "status": "ok",
        "signals_generated": generated,
        "skipped": skipped,
        "errors": errors,
        "model": f"{model_registry.model_name} {model_registry.version}",
    }
    if error_details:
        result["error_samples"] = error_details
    return result
