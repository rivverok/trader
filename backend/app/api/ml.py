"""API routes for ML signals, model management, and backtesting."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select, update
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
