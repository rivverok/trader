"""Celery tasks for ML signal generation and model retraining."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.celery_app import celery_app
from app.database import async_session

logger = logging.getLogger(__name__)

_ml_status: dict[str, dict[str, Any]] = {}


def _update_status(task_name: str, result: dict):
    _ml_status[task_name] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_result": result,
    }


def get_ml_status() -> dict[str, dict[str, Any]]:
    return dict(_ml_status)


def _run_async(coro):
    from app.database import engine
    asyncio.get_event_loop_policy().set_event_loop(loop := asyncio.new_event_loop())
    try:
        loop.run_until_complete(engine.dispose())
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Signal generation ────────────────────────────────────────────────

@celery_app.task(name="generate_ml_signals", bind=True, max_retries=1)
def generate_ml_signals(self):
    """Generate ML signals for all watchlist stocks using the active model."""
    try:
        from app.ml.technical_signals import generate_all_signals

        async def _generate():
            async with async_session() as session:
                return await generate_all_signals(db_session=session)

        result = _run_async(_generate())
        _update_status("generate_ml_signals", result)
        logger.info("generate_ml_signals: %s", result)
        return result
    except Exception as exc:
        _update_status("generate_ml_signals", {"status": "error", "error": str(exc)})
        logger.error("generate_ml_signals failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ── Model retraining ────────────────────────────────────────────────

@celery_app.task(name="retrain_model", bind=True, max_retries=0)
def retrain_model(self, symbols: list[str] | None = None, years: int = 5):
    """Retrain the ML model on latest data.

    This can be triggered manually or run on a weekly schedule.
    When run on the trading server, this re-trains using data in the database.
    """
    try:
        from app.ml.technical_signals import MODEL_DIR
        from app.models.ml import ModelRegistry
        from app.models.stock import Stock
        from sqlalchemy import select

        async def _get_watchlist_symbols():
            async with async_session() as session:
                result = await session.execute(
                    select(Stock.symbol).where(Stock.on_watchlist.is_(True))
                )
                return [row[0] for row in result.all()]

        if symbols is None:
            symbols = _run_async(_get_watchlist_symbols())
        if not symbols:
            result = {"status": "skip", "reason": "no symbols to train on"}
            _update_status("retrain_model", result)
            return result

        # Import training pipeline
        from training.train_technical_model import load_from_database, run_training

        df = load_from_database(symbols, years)

        def _progress_cb(symbol, sym_idx, total_symbols, fold_idx, total_folds, best_score, best_model_type):
            self.update_state(state="PROGRESS", meta={
                "current_symbol": symbol,
                "symbol_index": sym_idx + 1,
                "total_symbols": total_symbols,
                "fold_index": fold_idx + 1,
                "total_folds": total_folds,
                "best_score": round(best_score, 4) if best_score > 0 else None,
                "best_model_type": best_model_type or None,
            })

        report = run_training(df, progress_callback=_progress_cb)

        # Register the new model in the database
        # Auto-promote only if it outperforms the current active model
        async def _register_model():
            async with async_session() as session:
                from sqlalchemy import update, select as sa_select

                # Check current active model's validation metrics
                current = await session.execute(
                    sa_select(ModelRegistry)
                    .where(
                        ModelRegistry.model_name == report["model_name"],
                        ModelRegistry.is_active.is_(True),
                    )
                    .limit(1)
                )
                current_model = current.scalar_one_or_none()

                new_f1 = report["best_f1_macro"]
                should_activate = True

                if current_model and current_model.validation_metrics:
                    old_f1 = current_model.validation_metrics.get("best_f1_macro", 0)
                    if new_f1 <= old_f1:
                        should_activate = False
                        logger.info(
                            "New model f1=%.4f does NOT outperform current f1=%.4f — keeping current",
                            new_f1, old_f1,
                        )

                if should_activate:
                    # Deactivate all existing models of this type
                    await session.execute(
                        update(ModelRegistry)
                        .where(ModelRegistry.model_name == report["model_name"])
                        .values(is_active=False)
                    )

                new_model = ModelRegistry(
                    model_name=report["model_name"],
                    version=report["version"],
                    file_path=report["file_path"],
                    training_date=datetime.now(timezone.utc),
                    symbols_trained=",".join(report["symbols"]),
                    feature_count=report["feature_count"],
                    validation_metrics={
                        "best_f1_macro": report["best_f1_macro"],
                        "fold_metrics": report["fold_metrics"],
                        "top_features": report["top_feature_importances"],
                        "auto_promoted": should_activate,
                    },
                    is_active=should_activate,
                )
                session.add(new_model)
                await session.commit()

                # Fire alert for model retrain
                try:
                    from app.engine.alert_service import create_alert
                    status_msg = "promoted to active" if should_activate else "trained but NOT promoted (lower f1)"
                    await create_alert(
                        session, "model_retrained",
                        f"Model {report['model_name']} v{report['version']} retrained (f1={new_f1:.4f}) — {status_msg}",
                        severity="info",
                    )
                except Exception:
                    pass

                return should_activate

        promoted = _run_async(_register_model())

        result = {
            "status": "ok",
            "model": report["model_name"],
            "version": report["version"],
            "f1_macro": report["best_f1_macro"],
            "features": report["feature_count"],
        }
        _update_status("retrain_model", result)
        logger.info("retrain_model: %s", result)
        return result

    except Exception as exc:
        _update_status("retrain_model", {"status": "error", "error": str(exc)})
        logger.error("retrain_model failed: %s", exc)
        raise


# ── Backtest (manual trigger only) ──────────────────────────────────

@celery_app.task(name="run_backtest")
def run_backtest_task(
    model_path: str | None = None,
    symbols: list[str] | None = None,
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    initial_cash: float = 100_000.0,
):
    """Run a backtest and save results to the database."""
    try:
        from app.models.ml import BacktestResult, ModelRegistry
        from sqlalchemy import select

        # Find model path from active model if not specified
        if model_path is None:
            async def _get_active():
                async with async_session() as session:
                    result = await session.execute(
                        select(ModelRegistry)
                        .where(ModelRegistry.is_active.is_(True))
                        .limit(1)
                    )
                    m = result.scalar_one_or_none()
                    return m.file_path if m else None

            model_path = _run_async(_get_active())
            if model_path is None:
                return {"status": "error", "reason": "no active model"}

        # Get symbols from model artifact if not specified
        import joblib
        artifact = joblib.load(model_path)
        if symbols is None:
            symbols = artifact.get("symbols", [])
        if not symbols:
            return {"status": "error", "reason": "no symbols to backtest"}

        from training.backtest_strategies import load_prices_from_db, run_backtest

        price_data = load_prices_from_db(symbols, start_date, end_date)
        results = run_backtest(
            model_path=model_path,
            price_data=price_data,
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=end_date,
        )

        # Save to database
        agg = results["aggregate"]

        async def _save():
            async with async_session() as session:
                bt = BacktestResult(
                    strategy_name=results["strategy_name"],
                    model_name=results["model_name"],
                    model_version=results["model_version"],
                    symbols=",".join(results["symbols"]),
                    start_date=datetime.fromisoformat(start_date),
                    end_date=datetime.fromisoformat(end_date),
                    total_return=agg["avg_total_return"],
                    sharpe_ratio=agg["avg_sharpe_ratio"],
                    max_drawdown=agg["avg_max_drawdown"],
                    win_rate=agg["avg_win_rate"],
                    profit_factor=agg["avg_profit_factor"],
                    trades_count=agg["total_trades"],
                    benchmark_return=agg["avg_benchmark_return"],
                    report_json=results,
                )
                session.add(bt)
                await session.commit()

        _run_async(_save())

        result = {
            "status": "ok",
            "total_return": agg["avg_total_return"],
            "sharpe_ratio": agg["avg_sharpe_ratio"],
            "trades": agg["total_trades"],
        }
        _update_status("run_backtest", result)
        return result

    except Exception as exc:
        _update_status("run_backtest", {"status": "error", "error": str(exc)})
        logger.error("run_backtest failed: %s", exc)
        raise


# ── Model staleness check ───────────────────────────────────────────

@celery_app.task(name="check_model_staleness", max_retries=0)
def check_model_staleness():
    """Check if the active ML model is stale and create an alert if so."""
    import os
    from datetime import timedelta

    stale_days = int(os.environ.get("MODEL_STALE_DAYS", "14"))

    try:
        from app.models.ml import ModelRegistry
        from app.models.alert import Alert
        from sqlalchemy import select, desc, func

        async def _check():
            async with async_session() as session:
                # Get active model
                result = await session.execute(
                    select(ModelRegistry)
                    .where(ModelRegistry.is_active.is_(True))
                    .order_by(desc(ModelRegistry.training_date))
                    .limit(1)
                )
                active = result.scalar_one_or_none()

                if active is None:
                    age_days = None
                    is_stale = True
                    message = "No active ML model found. Run remote training to create one."
                else:
                    age = datetime.now(timezone.utc) - active.training_date.replace(
                        tzinfo=timezone.utc
                    )
                    age_days = age.days
                    is_stale = age_days > stale_days
                    if not is_stale:
                        return {"status": "ok", "age_days": age_days, "stale": False}
                    message = (
                        f"ML model is {age_days} days old (threshold: {stale_days}). "
                        f"Run remote training to update."
                    )

                # Check if we already fired a model_stale alert in the last 24h
                cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
                recent = await session.execute(
                    select(func.count())
                    .select_from(Alert)
                    .where(
                        Alert.type == "model_stale",
                        Alert.created_at >= cutoff_24h,
                    )
                )
                if recent.scalar() > 0:
                    return {"status": "already_alerted", "stale": True, "age_days": age_days}

                # Create alert
                from app.engine.alert_service import create_alert
                await create_alert(session, "model_stale", message, severity="warning")

                return {"status": "alerted", "stale": True, "age_days": age_days}

        result = _run_async(_check())
        _update_status("check_model_staleness", result)
        logger.info("check_model_staleness: %s", result)
        return result

    except Exception as exc:
        _update_status("check_model_staleness", {"status": "error", "error": str(exc)})
        logger.error("check_model_staleness failed: %s", exc)
        raise
