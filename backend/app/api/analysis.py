"""API routes for Claude analysis results and usage tracking."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import (
    ClaudeUsage,
    ContextSynthesis,
    FilingAnalysis,
    NewsAnalysis,
)
from app.models.news import NewsArticle
from app.models.sec_filing import SecFiling
from app.models.stock import Stock
from app.tasks.analysis_tasks import (
    analyze_filings,
    analyze_news_sentiment,
    get_analysis_status,
    run_context_synthesis,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ── Response schemas ─────────────────────────────────────────────────


class NewsAnalysisResponse(BaseModel):
    id: int
    headline: str
    published_at: str
    sentiment_score: float
    impact_severity: str
    material_event: bool
    summary: str

    class Config:
        from_attributes = True


class FilingAnalysisResponse(BaseModel):
    id: int
    filing_type: str
    filed_date: str
    revenue_trend: str | None
    margin_analysis: str | None
    risk_changes: str | None
    guidance_sentiment: float | None
    key_findings: list | None

    class Config:
        from_attributes = True


class SynthesisResponse(BaseModel):
    id: int
    overall_sentiment: float
    confidence: float
    key_factors: list | None
    risks: list | None
    opportunities: list | None
    reasoning_chain: str | None
    claude_model_used: str
    created_at: str

    class Config:
        from_attributes = True


class StockAnalysisResponse(BaseModel):
    symbol: str
    name: str | None
    latest_synthesis: SynthesisResponse | None
    recent_news: list[NewsAnalysisResponse]
    filing_analyses: list[FilingAnalysisResponse]


class UsageDayResponse(BaseModel):
    date: str
    task_type: str
    model: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    call_count: int


class UsageSummaryResponse(BaseModel):
    daily_breakdown: list[UsageDayResponse]
    total_cost_30d: float
    total_calls_30d: int


class AnalysisStatusResponse(BaseModel):
    tasks: dict


# ── Stock analysis detail ────────────────────────────────────────────


@router.get("/stocks/{symbol}", response_model=StockAnalysisResponse)
async def get_stock_analysis(symbol: str, db: AsyncSession = Depends(get_db)):
    """Get the latest synthesis + component analyses for a stock."""
    result = await db.execute(
        select(Stock).where(Stock.symbol == symbol.upper())
    )
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(404, detail=f"Stock {symbol} not found")

    # Latest synthesis
    synth_result = await db.execute(
        select(ContextSynthesis)
        .where(ContextSynthesis.stock_id == stock.id)
        .order_by(desc(ContextSynthesis.created_at))
        .limit(1)
    )
    synthesis = synth_result.scalar_one_or_none()

    # Recent news analyses (last 20)
    news_result = await db.execute(
        select(NewsArticle, NewsAnalysis)
        .join(NewsAnalysis, NewsAnalysis.article_id == NewsArticle.id)
        .where(NewsArticle.stock_id == stock.id)
        .order_by(desc(NewsArticle.published_at))
        .limit(20)
    )
    news_rows = news_result.all()

    # Filing analyses
    filing_result = await db.execute(
        select(SecFiling, FilingAnalysis)
        .join(FilingAnalysis, FilingAnalysis.filing_id == SecFiling.id)
        .where(SecFiling.stock_id == stock.id)
        .order_by(desc(SecFiling.filed_date))
        .limit(5)
    )
    filing_rows = filing_result.all()

    return StockAnalysisResponse(
        symbol=stock.symbol,
        name=stock.name,
        latest_synthesis=SynthesisResponse(
            id=synthesis.id,
            overall_sentiment=synthesis.overall_sentiment,
            confidence=synthesis.confidence,
            key_factors=synthesis.key_factors,
            risks=synthesis.risks,
            opportunities=synthesis.opportunities,
            reasoning_chain=synthesis.reasoning_chain,
            claude_model_used=synthesis.claude_model_used,
            created_at=synthesis.created_at.isoformat(),
        )
        if synthesis
        else None,
        recent_news=[
            NewsAnalysisResponse(
                id=analysis.id,
                headline=article.headline,
                published_at=article.published_at.isoformat(),
                sentiment_score=analysis.sentiment_score,
                impact_severity=analysis.impact_severity,
                material_event=analysis.material_event,
                summary=analysis.summary,
            )
            for article, analysis in news_rows
        ],
        filing_analyses=[
            FilingAnalysisResponse(
                id=fa.id,
                filing_type=filing.filing_type,
                filed_date=filing.filed_date.isoformat(),
                revenue_trend=fa.revenue_trend,
                margin_analysis=fa.margin_analysis,
                risk_changes=fa.risk_changes,
                guidance_sentiment=fa.guidance_sentiment,
                key_findings=fa.key_findings,
            )
            for filing, fa in filing_rows
        ],
    )


# ── Claude usage tracking ────────────────────────────────────────────


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get Claude API usage summary and cost breakdown."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(ClaudeUsage.date).label("day"),
            ClaudeUsage.task_type,
            ClaudeUsage.model,
            func.sum(ClaudeUsage.input_tokens).label("total_input"),
            func.sum(ClaudeUsage.output_tokens).label("total_output"),
            func.sum(ClaudeUsage.estimated_cost).label("total_cost"),
            func.count().label("call_count"),
        )
        .where(ClaudeUsage.date >= cutoff)
        .group_by(func.date(ClaudeUsage.date), ClaudeUsage.task_type, ClaudeUsage.model)
        .order_by(func.date(ClaudeUsage.date).desc())
    )
    rows = result.all()

    daily = [
        UsageDayResponse(
            date=str(row.day),
            task_type=row.task_type,
            model=row.model,
            total_input_tokens=row.total_input or 0,
            total_output_tokens=row.total_output or 0,
            total_cost=round(float(row.total_cost or 0), 4),
            call_count=row.call_count,
        )
        for row in rows
    ]

    total_cost = sum(d.total_cost for d in daily)
    total_calls = sum(d.call_count for d in daily)

    return UsageSummaryResponse(
        daily_breakdown=daily,
        total_cost_30d=round(total_cost, 4),
        total_calls_30d=total_calls,
    )


# ── Analysis pipeline status / manual trigger ────────────────────────


@router.get("/status", response_model=AnalysisStatusResponse)
async def analysis_status():
    """Get the status of analysis tasks."""
    return AnalysisStatusResponse(tasks=get_analysis_status())


@router.post("/trigger/{task_name}")
async def trigger_analysis(task_name: str):
    """Manually trigger an analysis task."""
    tasks = {
        "sentiment": analyze_news_sentiment,
        "filings": analyze_filings,
        "synthesis": run_context_synthesis,
    }
    task_fn = tasks.get(task_name)
    if task_fn is None:
        raise HTTPException(
            404,
            detail=f"Unknown task: {task_name}. Available: {list(tasks.keys())}",
        )
    result = task_fn.delay(force=True)
    return {"task_id": str(result.id), "task_name": task_name}
