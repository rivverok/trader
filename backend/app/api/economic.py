"""API routes for economic indicators."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.economic import EconomicIndicator

router = APIRouter(prefix="/api/economic-indicators", tags=["economic"])


class EconomicIndicatorResponse(BaseModel):
    indicator_code: str
    name: str
    value: float
    date: str
    source: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[EconomicIndicatorResponse])
async def list_economic_indicators(
    code: str | None = Query(None, description="Filter by indicator code"),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get latest economic indicator values."""
    query = select(EconomicIndicator).order_by(
        EconomicIndicator.indicator_code,
        desc(EconomicIndicator.date),
    )

    if code:
        query = query.where(EconomicIndicator.indicator_code == code.upper())

    # If no filter, get only the latest value per indicator
    if not code:
        from sqlalchemy import func, distinct

        subquery = (
            select(
                EconomicIndicator.indicator_code,
                func.max(EconomicIndicator.date).label("max_date"),
            )
            .group_by(EconomicIndicator.indicator_code)
            .subquery()
        )
        query = (
            select(EconomicIndicator)
            .join(
                subquery,
                (EconomicIndicator.indicator_code == subquery.c.indicator_code)
                & (EconomicIndicator.date == subquery.c.max_date),
            )
            .order_by(EconomicIndicator.indicator_code)
        )
    else:
        query = query.limit(limit)

    result = await db.execute(query)
    indicators = result.scalars().all()

    return [
        EconomicIndicatorResponse(
            indicator_code=i.indicator_code,
            name=i.name,
            value=i.value,
            date=i.date.isoformat(),
            source=i.source,
        )
        for i in indicators
    ]
