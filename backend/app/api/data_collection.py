"""API routes for RL data collection — snapshot status, manual triggers, export."""

import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.state_snapshots import (
    capture_snapshot,
    get_latest_snapshot,
    get_snapshot_count,
    get_snapshot_date_range,
    get_snapshot_stock_coverage,
)
from app.models.rl_snapshot import RLStateSnapshot, RLStockSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-collection", tags=["data-collection"])


# ── Schemas ──────────────────────────────────────────────────────────


class SnapshotSummary(BaseModel):
    id: int
    timestamp: str
    snapshot_type: str
    stock_count: int

    model_config = {"from_attributes": True}


class DataCollectionStatus(BaseModel):
    total_snapshots: int
    date_range: dict
    coverage: dict
    latest_snapshot: SnapshotSummary | None


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/status", response_model=DataCollectionStatus)
async def data_collection_status(db: AsyncSession = Depends(get_db)):
    """Overview of data collection progress — counts, coverage, latest snapshot."""
    total = await get_snapshot_count(db)
    date_range = await get_snapshot_date_range(db)
    coverage = await get_snapshot_stock_coverage(db)

    latest = await get_latest_snapshot(db)
    latest_summary = None
    if latest:
        # Count stocks in latest snapshot
        result = await db.execute(
            select(func.count(RLStockSnapshot.id))
            .where(RLStockSnapshot.snapshot_id == latest.id)
        )
        stock_count = result.scalar_one()
        latest_summary = SnapshotSummary(
            id=latest.id,
            timestamp=latest.timestamp.isoformat(),
            snapshot_type=latest.snapshot_type,
            stock_count=stock_count,
        )

    return DataCollectionStatus(
        total_snapshots=total,
        date_range=date_range,
        coverage=coverage,
        latest_snapshot=latest_summary,
    )


@router.get("/snapshots")
async def list_snapshots(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of state snapshots."""
    result = await db.execute(
        select(RLStateSnapshot)
        .order_by(RLStateSnapshot.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    snapshots = result.scalars().all()

    # Get stock counts per snapshot
    snapshot_ids = [s.id for s in snapshots]
    count_result = await db.execute(
        select(
            RLStockSnapshot.snapshot_id,
            func.count(RLStockSnapshot.id),
        )
        .where(RLStockSnapshot.snapshot_id.in_(snapshot_ids))
        .group_by(RLStockSnapshot.snapshot_id)
    )
    stock_counts = dict(count_result.all())

    total_result = await db.execute(
        select(func.count(RLStateSnapshot.id))
    )
    total = total_result.scalar_one()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "snapshots": [
            {
                "id": s.id,
                "timestamp": s.timestamp.isoformat(),
                "snapshot_type": s.snapshot_type,
                "stock_count": stock_counts.get(s.id, 0),
                "portfolio_value": s.portfolio_state.get("total_value")
                if s.portfolio_state else None,
            }
            for s in snapshots
        ],
    }


@router.post("/snapshot")
async def trigger_snapshot(db: AsyncSession = Depends(get_db)):
    """Manually trigger a state snapshot capture."""
    snapshot = await capture_snapshot(db, snapshot_type="manual")
    if not snapshot:
        raise HTTPException(400, detail="Snapshot failed — no watchlist stocks or data")

    result = await db.execute(
        select(func.count(RLStockSnapshot.id))
        .where(RLStockSnapshot.snapshot_id == snapshot.id)
    )
    stock_count = result.scalar_one()

    return {
        "status": "ok",
        "snapshot_id": snapshot.id,
        "timestamp": snapshot.timestamp.isoformat(),
        "stock_count": stock_count,
    }


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot_detail(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full detail of a single snapshot including all stock data."""
    result = await db.execute(
        select(RLStateSnapshot).where(RLStateSnapshot.id == snapshot_id)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, detail="Snapshot not found")

    result = await db.execute(
        select(RLStockSnapshot)
        .where(RLStockSnapshot.snapshot_id == snapshot_id)
        .order_by(RLStockSnapshot.symbol)
    )
    stocks = result.scalars().all()

    return {
        "id": snapshot.id,
        "timestamp": snapshot.timestamp.isoformat(),
        "snapshot_type": snapshot.snapshot_type,
        "portfolio_state": snapshot.portfolio_state,
        "market_state": snapshot.market_state,
        "metadata": snapshot.metadata_,
        "stocks": [
            {
                "symbol": s.symbol,
                "price_data": s.price_data,
                "technical_indicators": s.technical_indicators,
                "ml_signal": s.ml_signal,
                "sentiment": s.sentiment,
                "synthesis": s.synthesis,
                "analyst_input": s.analyst_input,
                "relative_strength": s.relative_strength,
            }
            for s in stocks
        ],
    }


@router.get("/export")
async def export_snapshots(
    format: str = Query("json", pattern=r"^(json|parquet)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export all snapshots as JSON or Parquet for RL training."""
    result = await db.execute(
        select(RLStateSnapshot).order_by(RLStateSnapshot.timestamp.asc())
    )
    snapshots = result.scalars().all()

    if not snapshots:
        raise HTTPException(404, detail="No snapshots to export")

    if format == "parquet":
        return await _export_parquet(db, snapshots)

    # JSON export
    data = []
    for snap in snapshots:
        stocks_result = await db.execute(
            select(RLStockSnapshot)
            .where(RLStockSnapshot.snapshot_id == snap.id)
        )
        stocks = stocks_result.scalars().all()
        data.append({
            "timestamp": snap.timestamp.isoformat(),
            "snapshot_type": snap.snapshot_type,
            "portfolio_state": snap.portfolio_state,
            "market_state": snap.market_state,
            "stocks": {
                s.symbol: {
                    "price_data": s.price_data,
                    "technical_indicators": s.technical_indicators,
                    "ml_signal": s.ml_signal,
                    "sentiment": s.sentiment,
                    "synthesis": s.synthesis,
                    "analyst_input": s.analyst_input,
                    "relative_strength": s.relative_strength,
                }
                for s in stocks
            },
        })

    import json
    content = json.dumps(data, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=rl_snapshots.json"},
    )


async def _export_parquet(
    db: AsyncSession,
    snapshots: list[RLStateSnapshot],
) -> StreamingResponse:
    """Export snapshots in Parquet format — one row per stock per snapshot."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise HTTPException(
            500, detail="pyarrow not installed — cannot export Parquet"
        )

    rows = []
    for snap in snapshots:
        stocks_result = await db.execute(
            select(RLStockSnapshot)
            .where(RLStockSnapshot.snapshot_id == snap.id)
        )
        stocks = stocks_result.scalars().all()
        for s in stocks:
            row = {
                "timestamp": snap.timestamp.isoformat(),
                "snapshot_type": snap.snapshot_type,
                "symbol": s.symbol,
                # Flatten key price fields
                "close": s.price_data.get("close") if s.price_data else None,
                "volume": s.price_data.get("volume") if s.price_data else None,
                "return_1d": s.price_data.get("return_1d") if s.price_data else None,
                "return_5d": s.price_data.get("return_5d") if s.price_data else None,
                # ML signal
                "ml_signal": s.ml_signal.get("signal") if s.ml_signal else None,
                "ml_confidence": s.ml_signal.get("confidence") if s.ml_signal else None,
                # Sentiment
                "sentiment_score": s.sentiment.get("avg_score") if s.sentiment else None,
                "material_events": s.sentiment.get("material_events") if s.sentiment else None,
                # Synthesis
                "synthesis_sentiment": s.synthesis.get("overall_sentiment") if s.synthesis else None,
                "synthesis_confidence": s.synthesis.get("confidence") if s.synthesis else None,
                # Portfolio context
                "portfolio_value": snap.portfolio_state.get("total_value") if snap.portfolio_state else None,
                "cash_pct": snap.portfolio_state.get("cash_pct") if snap.portfolio_state else None,
            }
            rows.append(row)

    import pandas as pd
    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df)

    buf = io.BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=rl_snapshots.parquet"},
    )
