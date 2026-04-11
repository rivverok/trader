"""API routes for ML signals, model management, and backtesting."""

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ml import BacktestResult, ModelRegistry
from app.models.signal import MLSignal
from app.models.stock import Stock
from app.tasks.ml_tasks import (
    generate_ml_signals,
    get_ml_status,
    retrain_model,
    run_backtest_task,
)

router = APIRouter(prefix="/api", tags=["ml"])


# ── Response schemas ─────────────────────────────────────────────────


class MLSignalResponse(BaseModel):
    id: int
    signal: str
    confidence: float
    model_name: str
    model_version: str
    feature_importances: dict | None
    created_at: str

    class Config:
        from_attributes = True


class ModelResponse(BaseModel):
    id: int
    model_name: str
    version: str
    file_path: str
    training_date: str
    symbols_trained: str
    feature_count: int
    validation_metrics: dict | None
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class BacktestResultResponse(BaseModel):
    id: int
    strategy_name: str
    model_name: str | None
    model_version: str | None
    symbols: str
    start_date: str
    end_date: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trades_count: int
    benchmark_return: float | None
    report_json: dict | None
    created_at: str

    class Config:
        from_attributes = True


class BacktestRunRequest(BaseModel):
    symbols: list[str] | None = None
    start_date: str = "2021-01-01"
    end_date: str = "2025-12-31"
    initial_cash: float = 100_000.0


class RetrainRequest(BaseModel):
    symbols: list[str] | None = None
    years: int = 5


# ── Signal endpoints ─────────────────────────────────────────────────


@router.get("/stocks/{symbol}/signals", response_model=list[MLSignalResponse])
async def get_stock_signals(
    symbol: str,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get latest ML signals for a stock."""
    result = await db.execute(
        select(Stock).where(Stock.symbol == symbol.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"Stock {symbol} not found")

    result = await db.execute(
        select(MLSignal)
        .where(MLSignal.stock_id == stock.id)
        .order_by(desc(MLSignal.created_at))
        .limit(limit)
    )
    signals = result.scalars().all()

    return [
        MLSignalResponse(
            id=s.id,
            signal=s.signal,
            confidence=s.confidence,
            model_name=s.model_name,
            model_version=s.model_version,
            feature_importances=s.feature_importances,
            created_at=s.created_at.isoformat(),
        )
        for s in signals
    ]


# ── Model management endpoints ───────────────────────────────────────


@router.get("/models", response_model=list[ModelResponse])
async def list_models(db: AsyncSession = Depends(get_db)):
    """List all trained models with validation metrics."""
    result = await db.execute(
        select(ModelRegistry).order_by(desc(ModelRegistry.training_date))
    )
    models = result.scalars().all()
    return [
        ModelResponse(
            id=m.id,
            model_name=m.model_name,
            version=m.version,
            file_path=m.file_path,
            training_date=m.training_date.isoformat(),
            symbols_trained=m.symbols_trained,
            feature_count=m.feature_count,
            validation_metrics=m.validation_metrics,
            is_active=m.is_active,
            created_at=m.created_at.isoformat(),
        )
        for m in models
    ]


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the active model (deactivates others of same type)."""
    result = await db.execute(
        select(ModelRegistry).where(ModelRegistry.id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, detail="Model not found")

    # Deactivate all models of the same name
    await db.execute(
        update(ModelRegistry)
        .where(ModelRegistry.model_name == model.model_name)
        .values(is_active=False)
    )
    # Activate the selected one
    model.is_active = True
    await db.commit()

    return {"status": "ok", "activated": f"{model.model_name} {model.version}"}


@router.post("/models/retrain")
async def trigger_retrain(body: RetrainRequest):
    """Trigger model retraining manually."""
    result = retrain_model.delay(symbols=body.symbols, years=body.years)
    return {"task_id": str(result.id), "status": "queued"}


@router.post("/models/generate-signals")
async def trigger_generate_signals():
    """Trigger ML signal generation for all watchlist stocks."""
    result = generate_ml_signals.delay(force=True)
    return {"task_id": str(result.id), "status": "queued"}


# ── Backtest endpoints ───────────────────────────────────────────────


@router.get("/backtest/results", response_model=list[BacktestResultResponse])
async def list_backtest_results(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List backtest runs with metrics."""
    result = await db.execute(
        select(BacktestResult)
        .order_by(desc(BacktestResult.created_at))
        .limit(limit)
    )
    runs = result.scalars().all()
    return [
        BacktestResultResponse(
            id=r.id,
            strategy_name=r.strategy_name,
            model_name=r.model_name,
            model_version=r.model_version,
            symbols=r.symbols,
            start_date=r.start_date.isoformat(),
            end_date=r.end_date.isoformat(),
            total_return=r.total_return,
            sharpe_ratio=r.sharpe_ratio,
            max_drawdown=r.max_drawdown,
            win_rate=r.win_rate,
            profit_factor=r.profit_factor,
            trades_count=r.trades_count,
            benchmark_return=r.benchmark_return,
            report_json=r.report_json,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.post("/backtest/run")
async def trigger_backtest(body: BacktestRunRequest):
    """Trigger a new backtest with configurable parameters."""
    result = run_backtest_task.delay(
        symbols=body.symbols,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_cash=body.initial_cash,
    )
    return {"task_id": str(result.id), "status": "queued"}


# ── ML pipeline status ──────────────────────────────────────────────


@router.get("/ml/status")
async def ml_status():
    """Get the status of ML tasks."""
    return {"tasks": get_ml_status()}


# ── Remote training endpoints ────────────────────────────────────────

MODEL_STALE_DAYS = int(os.environ.get("MODEL_STALE_DAYS", "14"))
UPLOAD_DIR = Path("/app/data/ml/models")


@router.get("/models/training-data")
async def export_training_data(
    years: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Export OHLCV price data for all watchlist stocks as streaming CSV."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=years * 365)

    result = await db.execute(
        text("""
            SELECT s.symbol, p.timestamp, p.open, p.high, p.low, p.close, p.volume
            FROM prices p
            JOIN stocks s ON s.id = p.stock_id
            WHERE s.on_watchlist = TRUE
              AND p.interval = '1Day'
              AND p.timestamp >= :cutoff
            ORDER BY s.symbol, p.timestamp
        """),
        {"cutoff": cutoff},
    )
    rows = result.all()

    if not rows:
        raise HTTPException(404, detail="No price data found for watchlist stocks")

    def generate_csv():
        yield "symbol,timestamp,open,high,low,close,volume\n"
        for row in rows:
            ts = row.timestamp.isoformat() if hasattr(row.timestamp, "isoformat") else str(row.timestamp)
            yield f"{row.symbol},{ts},{row.open},{row.high},{row.low},{row.close},{row.volume}\n"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=training_data.csv"},
    )


@router.get("/models/staleness")
async def check_staleness(db: AsyncSession = Depends(get_db)):
    """Check if the active ML model is stale and needs retraining."""
    result = await db.execute(
        select(ModelRegistry)
        .where(ModelRegistry.is_active.is_(True))
        .order_by(desc(ModelRegistry.training_date))
        .limit(1)
    )
    active = result.scalar_one_or_none()

    if active is None:
        return {
            "stale": True,
            "reason": "no_active_model",
            "active_model_age_days": None,
            "active_model_f1": None,
            "last_training_date": None,
            "threshold_days": MODEL_STALE_DAYS,
        }

    age = datetime.now(timezone.utc) - active.training_date.replace(tzinfo=timezone.utc)
    age_days = age.days
    f1 = active.validation_metrics.get("best_f1_macro") if active.validation_metrics else None

    return {
        "stale": age_days > MODEL_STALE_DAYS,
        "reason": "model_too_old" if age_days > MODEL_STALE_DAYS else "ok",
        "active_model_age_days": age_days,
        "active_model_f1": f1,
        "last_training_date": active.training_date.isoformat(),
        "threshold_days": MODEL_STALE_DAYS,
        "active_model": {
            "id": active.id,
            "model_name": active.model_name,
            "version": active.version,
        },
    }


@router.post("/models/upload")
async def upload_model(
    model_file: UploadFile = File(...),
    report_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a remotely-trained model artifact and report.

    Accepts a .joblib model file and a .json report file.
    Auto-promotes the model if its F1 score beats the current active model.
    """
    if not model_file.filename or not model_file.filename.endswith(".joblib"):
        raise HTTPException(400, detail="model_file must be a .joblib file")
    if not report_file.filename or not report_file.filename.endswith(".json"):
        raise HTTPException(400, detail="report_file must be a .json file")

    # Read report
    report_bytes = await report_file.read()
    try:
        report = json.loads(report_bytes)
    except json.JSONDecodeError:
        raise HTTPException(400, detail="Invalid JSON in report file")

    # Validate required report fields
    required_fields = ["model_name", "version", "best_f1_macro", "symbols", "feature_count"]
    missing = [f for f in required_fields if f not in report]
    if missing:
        raise HTTPException(400, detail=f"Report missing fields: {missing}")

    # Save files to persistent volume
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    model_path = UPLOAD_DIR / model_file.filename
    report_path = UPLOAD_DIR / report_file.filename

    model_bytes = await model_file.read()
    model_path.write_bytes(model_bytes)
    report_path.write_bytes(report_bytes)

    # Auto-promotion logic (same as ml_tasks.py retrain_model)
    new_f1 = report["best_f1_macro"]
    should_activate = True

    current = await db.execute(
        select(ModelRegistry)
        .where(
            ModelRegistry.model_name == report["model_name"],
            ModelRegistry.is_active.is_(True),
        )
        .limit(1)
    )
    current_model = current.scalar_one_or_none()
    old_f1 = None

    if current_model and current_model.validation_metrics:
        old_f1 = current_model.validation_metrics.get("best_f1_macro", 0)
        if new_f1 <= old_f1:
            should_activate = False

    if should_activate:
        await db.execute(
            update(ModelRegistry)
            .where(ModelRegistry.model_name == report["model_name"])
            .values(is_active=False)
        )

    symbols = report.get("symbols", [])
    new_model = ModelRegistry(
        model_name=report["model_name"],
        version=report["version"],
        file_path=str(model_path),
        training_date=datetime.now(timezone.utc),
        symbols_trained=",".join(symbols) if isinstance(symbols, list) else str(symbols),
        feature_count=report.get("feature_count", 0),
        validation_metrics={
            "best_f1_macro": new_f1,
            "fold_metrics": report.get("fold_metrics", []),
            "top_features": report.get("top_feature_importances", {}),
            "auto_promoted": should_activate,
            "source": "remote_upload",
        },
        is_active=should_activate,
    )
    db.add(new_model)
    await db.commit()

    # Create alert
    try:
        from app.engine.alert_service import create_alert
        status = "promoted to active" if should_activate else "uploaded but NOT promoted (lower f1)"
        await create_alert(
            db, "model_retrained",
            f"Remote model {report['model_name']} v{report['version']} "
            f"(f1={new_f1:.4f}) — {status}",
            severity="info",
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "promoted": should_activate,
        "new_f1": new_f1,
        "old_f1": old_f1,
        "model_name": report["model_name"],
        "version": report["version"],
        "file_path": str(model_path),
    }
