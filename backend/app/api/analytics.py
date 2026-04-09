"""API routes for performance analytics and signal attribution."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.analytics import calculate_performance, calculate_attribution

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/performance")
async def performance_metrics(db: AsyncSession = Depends(get_db)):
    """Sharpe ratio, max drawdown, win rate, profit factor, Calmar ratio,
    monthly returns, and equity curve."""
    return await calculate_performance(db)


@router.get("/attribution")
async def signal_attribution(db: AsyncSession = Depends(get_db)):
    """Which signal source (ML, Claude, analyst) contributed most to
    winning vs. losing trades."""
    return await calculate_attribution(db)
